"""RED (M12 Task 1): claims audit rows lack ip/user_agent.

Claim actions (submit/cancel/approve) write ``AuditLog`` directly via
``ClaimRepository.add_audit`` (see app/infrastructure/persistence/claim_repository.py),
constructing the ORM row with no ``ip_address``/``user_agent`` at all. Every OTHER
mutation flows through the Unit of Work's domain-event dispatch, where
``AuditLogHandler`` (app/infrastructure/event_dispatcher.py) enriches those two
columns from the request-scoped ``RequestMeta`` ContextVar (app/core/request_meta.py),
itself populated by ``RequestMetaMiddleware`` from the real HTTP request. Because
claims bypass that dispatcher, their audit_logs rows have NULL ip_address/user_agent
even when the action was taken over a real HTTP request with a real client IP and
User-Agent header.

Mirrors tests/integration/test_audit_request_meta.py exactly for how a real HTTP
request yields a non-null ip in the test environment: only JWT *verification* is
stubbed (get_current_user override reads the user id straight out of the
Authorization header, as test_relationship_update_validation.py / test_audit_
request_meta.py do) -- real TestClient/ASGITransport requests still flow through
the actual RequestMetaMiddleware, LanguageMiddleware, etc., so the ContextVar is
genuinely populated by the app's own middleware stack, not faked.

Task 2 (not this task) fixes the bypass by routing claim audits through the
dispatcher. These tests should flip from RED to GREEN once that lands, with NO
changes to this file.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


@pytest.fixture()
async def session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture()
async def seeded(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """A clan, an approved admin, an approved viewer (the submitter/claimant), and a
    live person owned by that clan -- the minimum wiring for the claim actions under
    test, mirroring tests/integration/test_claim_approval.py's raw-SQL seeding."""
    clan_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    submitter_id = uuid.uuid4()
    person_id = uuid.uuid4()
    now = datetime.now(UTC)

    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Claims Clan', :slug)"),
            {"id": clan_id, "slug": f"claims-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :email, :name)"
            ),
            {"id": admin_id, "email": f"{admin_id.hex[:8]}@example.com", "name": "admin"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :email, :name)"
            ),
            {
                "id": submitter_id,
                "email": f"{submitter_id.hex[:8]}@example.com",
                "name": "claimant",
            },
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:uid, :cid, 'admin', true, :uid, :now)"
            ),
            {"uid": admin_id, "cid": clan_id, "now": now},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:uid, :cid, 'viewer', true, :approved_by, :now)"
            ),
            {"uid": submitter_id, "cid": clan_id, "approved_by": admin_id, "now": now},
        )
        await s.execute(
            sa.text(
                "INSERT INTO persons "
                "(id, full_name, created_by_clan_id, created_by, updated_by) "
                "VALUES (:id, :name, :clan_id, :created_by, :updated_by)"
            ),
            {
                "id": person_id,
                "name": "Person Under Claim",
                "clan_id": clan_id,
                "created_by": admin_id,
                "updated_by": admin_id,
            },
        )
        await s.commit()

    return {
        "clan_id": clan_id,
        "admin_id": admin_id,
        "submitter_id": submitter_id,
        "person_id": person_id,
    }


@pytest.fixture()
def admin_headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['admin_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
        "User-Agent": "FamilyRootsClaimsTest/1.0",
    }


@pytest.fixture()
def submitter_headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['submitter_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
        "User-Agent": "FamilyRootsClaimsTest/1.0",
    }


async def _seed_pending_claim(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    claim_id: uuid.UUID,
    user_id: uuid.UUID,
    person_id: uuid.UUID,
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO identity_claims "
                "(id, user_id, person_id, status, requester_note, created_at, updated_at) "
                "VALUES (:id, :uid, :pid, 'PENDING', :note, :now, :now)"
            ),
            {
                "id": claim_id,
                "uid": user_id,
                "pid": person_id,
                "note": "I am this person",
                "now": now,
            },
        )
        await s.commit()


async def _audit_rows(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    action: str,
    resource_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """All audit_logs rows for this exact action + resource_id (avoids cross-test
    contamination in the shared session-scoped test DB)."""
    async with session_factory() as s:
        rows = (
            (
                await s.execute(
                    sa.text(
                        "SELECT ip_address, user_agent, action, resource_type, resource_id, "
                        "old_value, new_value FROM audit_logs "
                        "WHERE action = :action AND resource_id = :rid "
                        "ORDER BY created_at ASC"
                    ),
                    {"action": action, "rid": resource_id},
                )
            )
            .mappings()
            .all()
        )
        result = []
        for row in rows:
            d = dict(row)
            # psycopg returns INET columns as ipaddress.IPv4Address/IPv6Address, not str.
            if d["ip_address"] is not None:
                d["ip_address"] = str(d["ip_address"])
            result.append(d)
        return result


async def test_claim_submit_audit_has_ip_and_user_agent(
    client: AsyncClient,
    submitter_headers: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
) -> None:
    """POST /persons/{id}/claim over real HTTP -> RequestMetaMiddleware sets the
    ContextVar -> but claim.submit's audit row is written directly by
    ClaimRepository.add_audit, bypassing the enriching dispatcher.

    RED today: ip_address/user_agent are both NULL.
    """
    resp = await client.post(
        f"/api/v1/persons/{seeded['person_id']}/claim",
        json={"requester_note": "I am this person"},
        headers=submitter_headers,
    )
    assert resp.status_code == 201, resp.text
    claim_id = uuid.UUID(resp.json()["data"]["id"])

    rows = await _audit_rows(session_factory, action="claim.submit", resource_id=claim_id)
    assert len(rows) == 1, f"expected exactly one claim.submit audit row, got {rows}"
    row = rows[0]

    assert row["ip_address"] is not None, f"expected non-null ip_address, got {row}"
    assert row["user_agent"] is not None, f"expected non-null user_agent, got {row}"


async def _approve_over_http(
    client: AsyncClient,
    *,
    clan_id: uuid.UUID,
    claim_id: uuid.UUID,
    headers: dict[str, str],
) -> None:
    """POST the approve endpoint and require a clean 200.

    Task 2 folded in the post-commit MissingGreenlet fix (approve_claim now refreshes
    the UPDATE-expired ``updated_at``/``created_at`` before ``model_validate``), so the
    endpoint returns a real ``IdentityClaimResponse`` instead of raising a pydantic
    ValidationError after an already-durable commit. No tolerance needed anymore.
    """
    resp = await client.post(
        f"/api/v1/clans/{clan_id}/claims/{claim_id}/approve",
        json={"reviewer_note": "looks right"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


async def test_claim_approve_audit_has_ip_and_user_agent(
    client: AsyncClient,
    admin_headers: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
) -> None:
    """Admin approves a pending claim over real HTTP -> claim.approve audit row
    should carry ip/UA. RED today: bypasses the enriching dispatcher.
    """
    claim_id = uuid.uuid4()
    await _seed_pending_claim(
        session_factory,
        claim_id=claim_id,
        user_id=seeded["submitter_id"],
        person_id=seeded["person_id"],
    )

    await _approve_over_http(
        client, clan_id=seeded["clan_id"], claim_id=claim_id, headers=admin_headers
    )

    rows = await _audit_rows(session_factory, action="claim.approve", resource_id=claim_id)
    assert len(rows) == 1, f"expected exactly one claim.approve audit row, got {rows}"
    row = rows[0]

    assert row["ip_address"] is not None, f"expected non-null ip_address, got {row}"
    assert row["user_agent"] is not None, f"expected non-null user_agent, got {row}"


async def test_claim_cancel_writes_audit_with_ip(
    client: AsyncClient,
    submitter_headers: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
) -> None:
    """Owner cancels their own pending claim over real HTTP -> exactly one
    claim.cancel audit row must exist, and it should carry ip/UA.

    RED today: bypasses the enriching dispatcher (also pins that a claim.cancel
    audit row is written at all).
    """
    claim_id = uuid.uuid4()
    await _seed_pending_claim(
        session_factory,
        claim_id=claim_id,
        user_id=seeded["submitter_id"],
        person_id=seeded["person_id"],
    )

    resp = await client.delete(
        f"/api/v1/claims/{claim_id}",
        headers=submitter_headers,
    )
    assert resp.status_code == 204, resp.text

    rows = await _audit_rows(session_factory, action="claim.cancel", resource_id=claim_id)
    assert len(rows) == 1, f"expected exactly one claim.cancel audit row, got {rows}"
    row = rows[0]

    assert row["ip_address"] is not None, f"expected non-null ip_address, got {row}"
    assert row["user_agent"] is not None, f"expected non-null user_agent, got {row}"


async def test_claim_audit_content_preserved(
    client: AsyncClient,
    admin_headers: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
) -> None:
    """Control: claim.approve's audit row keeps the right action/resource_type/
    resource_id/old_value/new_value regardless of ip/UA enrichment. Must stay
    green both before AND after Task 2 -- only the ip/UA columns should change.
    """
    claim_id = uuid.uuid4()
    await _seed_pending_claim(
        session_factory,
        claim_id=claim_id,
        user_id=seeded["submitter_id"],
        person_id=seeded["person_id"],
    )

    await _approve_over_http(
        client, clan_id=seeded["clan_id"], claim_id=claim_id, headers=admin_headers
    )

    rows = await _audit_rows(session_factory, action="claim.approve", resource_id=claim_id)
    assert len(rows) == 1, f"expected exactly one claim.approve audit row, got {rows}"
    row = rows[0]

    assert row["action"] == "claim.approve"
    assert row["resource_type"] == "identity_claim"
    assert row["resource_id"] == claim_id
    assert row["old_value"] == {"status": "PENDING"}
    assert row["new_value"] == {"status": "APPROVED", "person_id": str(seeded["person_id"])}
