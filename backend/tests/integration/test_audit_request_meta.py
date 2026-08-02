"""audit_logs rows carry the requester's ip/user-agent (spec 2026-07-14).

Real Postgres (migrated_db_url), real RBAC. Only JWT *verification* is stubbed
(mirrors tests/integration/test_relationship_update_validation.py) — the
Authorization header carries the user id directly instead of a signed token,
so these tests focus on request-meta propagation into audit rows, not auth.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.domain.shared.events import AuditableEvent
from app.infrastructure.event_dispatcher import create_event_dispatcher
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
async def seeded(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """A clan plus an approved editor membership."""
    clan_id = uuid.uuid4()
    editor_id = uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Meta Clan', :slug)"),
            {"id": clan_id, "slug": f"meta-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :email, :name)"
            ),
            {"id": editor_id, "email": f"{editor_id.hex[:8]}@example.com", "name": "editor"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:uid, :cid, 'editor', true, :uid, now())"
            ),
            {"uid": editor_id, "cid": clan_id},
        )
        await s.commit()
    return {"clan_id": clan_id, "editor_id": editor_id}


def _make_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[AsyncClient, Any]:
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver"), app


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    ac, _ = _make_client(session_factory)
    async with ac:
        yield ac


@pytest.fixture()
async def client_trusting_proxy(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncClient]:
    """A second app instance built with RATE_LIMIT_TRUST_FORWARDED_FOR flipped on.

    Both RateLimitMiddleware and RequestMetaMiddleware capture the trust flag at
    ``create_app()`` construction time (read once from the ``settings`` singleton,
    app/core/config.py), not per-request — mirroring RateLimitMiddleware's existing
    ``trust_forwarded_for`` constructor param. So the monkeypatch only needs to be
    active for this one ``create_app()`` call; the resulting app's middleware keeps
    trust=True for its whole lifetime regardless of later global settings changes,
    letting this fixture and the plain ``client`` fixture coexist correctly within
    the same test.
    """
    with monkeypatch.context() as m:
        m.setattr(settings, "RATE_LIMIT_TRUST_FORWARDED_FOR", True)
        ac, _ = _make_client(session_factory)
    async with ac:
        yield ac


@pytest.fixture()
def editor_headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['editor_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


async def _latest_audit(
    session_factory: async_sessionmaker[AsyncSession], clan_id: uuid.UUID
) -> dict[str, Any]:
    async with session_factory() as s:
        row = (
            (
                await s.execute(
                    sa.text(
                        "SELECT ip_address, user_agent FROM audit_logs "
                        "WHERE clan_id = :c ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"c": clan_id},
                )
            )
            .mappings()
            .first()
        )
        assert row is not None, "expected an audit_logs row to have been written"
        result = dict(row)
        # psycopg returns INET columns as ipaddress.IPv4Address/IPv6Address, not str.
        if result["ip_address"] is not None:
            result["ip_address"] = str(result["ip_address"])
        return result


async def test_http_mutation_audit_row_has_ip_and_ua(
    client: AsyncClient,
    editor_headers: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
) -> None:
    resp = await client.post(
        "/api/v1/persons",
        json={"full_name": "Cụ Test", "gender": "male"},
        headers={**editor_headers, "User-Agent": "FamilyRootsTest/1.0"},
    )
    assert resp.status_code == 201, resp.text

    row = await _latest_audit(session_factory, seeded["clan_id"])
    assert row["user_agent"] == "FamilyRootsTest/1.0"
    assert row["ip_address"] is not None


async def test_xff_honored_only_when_trusted(
    client_trusting_proxy: AsyncClient,
    client: AsyncClient,
    editor_headers: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
) -> None:
    xff_headers = {**editor_headers, "X-Forwarded-For": "1.2.3.4, 5.6.7.8"}

    resp = await client_trusting_proxy.post(
        "/api/v1/persons",
        json={"full_name": "Trusted Proxy Person", "gender": "male"},
        headers=xff_headers,
    )
    assert resp.status_code == 201, resp.text
    trusted_row = await _latest_audit(session_factory, seeded["clan_id"])
    assert trusted_row["ip_address"] == "5.6.7.8"

    resp = await client.post(
        "/api/v1/persons",
        json={"full_name": "Untrusted Proxy Person", "gender": "male"},
        headers=xff_headers,
    )
    assert resp.status_code == 201, resp.text
    untrusted_row = await _latest_audit(session_factory, seeded["clan_id"])
    assert untrusted_row["ip_address"] != "5.6.7.8"


async def test_out_of_request_audit_rows_are_null(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """No HTTP request in flight (e.g. a scheduler/purge job) -> NULL columns."""
    clan_id, actor_id = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Sched Clan', :slug)"),
            {"id": clan_id, "slug": f"sched-{clan_id.hex[:8]}"},
        )
        await s.commit()

        dispatcher = create_event_dispatcher(s)
        event = AuditableEvent(
            clan_id=clan_id,
            actor_id=actor_id,
            actor_role="system",
            action="scheduler.test",
            resource_type="test",
        )
        await dispatcher.dispatch([event])
        await s.commit()

    row = await _latest_audit(session_factory, clan_id)
    assert row["ip_address"] is None
    assert row["user_agent"] is None


async def test_long_user_agent_truncated(
    client: AsyncClient,
    editor_headers: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
) -> None:
    ua = "X" * 800
    resp = await client.post(
        "/api/v1/persons",
        json={"full_name": "Long UA Person", "gender": "male"},
        headers={**editor_headers, "User-Agent": ua},
    )
    assert resp.status_code == 201, resp.text

    row = await _latest_audit(session_factory, seeded["clan_id"])
    assert row["user_agent"] is not None
    assert len(row["user_agent"]) == 500
