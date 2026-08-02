"""Optimistic concurrency on PATCH /persons/{id} (H1).

Real Postgres (migrated_db_url), real RBAC (require_role queries user_clan_roles),
real Person aggregate + repository. Only JWT *verification* is stubbed — the
Authorization header carries the user id directly instead of a signed token, so the
test focuses on the OCC contract rather than re-proving auth (already covered by
test_auth_http_flow.py).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.person.commands import UpdatePerson
from app.application.person.handlers import PersonCommandHandler
from app.core.database import get_db
from app.core.security import get_current_user
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.person_repository import SqlAlchemyPersonRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Test-only stub: the bearer token IS the user id (no signature verification).

    RBAC (require_role / get_current_clan_id) still runs for real against the
    seeded DB rows below, so role gating isn't bypassed — only token signing is.
    """
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
    """A clan plus an approved editor and an approved admin membership."""
    clan_id = uuid.uuid4()
    editor_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'OCC Clan', :slug)"),
            {"id": clan_id, "slug": f"occ-{clan_id.hex[:8]}"},
        )
        for uid, role in ((editor_id, "editor"), (admin_id, "admin")):
            await s.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name) "
                    "VALUES (:id, :email, :name)"
                ),
                {"id": uid, "email": f"{uid.hex[:8]}@example.com", "name": role},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:uid, :cid, :role, true, :uid, now())"
                ),
                {"uid": uid, "cid": clan_id, "role": role},
            )
        await s.commit()
    return {"clan_id": clan_id, "editor_id": editor_id, "admin_id": admin_id}


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
def editor_headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['editor_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


@pytest.fixture()
def admin_headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['admin_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


@pytest.fixture()
async def person_id(client: AsyncClient, editor_headers: dict[str, str]) -> str:
    resp = await client.post(
        "/api/v1/persons",
        headers=editor_headers,
        json={"full_name": "Cụ Occ", "gender": "male"},
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


@pytest.fixture()
def make_update(
    seeded: dict[str, Any],
) -> Callable[[str, dict[str, Any], int], UpdatePerson]:
    """Closure binding clan_id/actor so tests only vary person_id/changes/version."""
    actor = ActorInfo(user_id=seeded["editor_id"], role="editor")

    def _make(person_id: str, changes: dict[str, Any], expected_version: int) -> UpdatePerson:
        return UpdatePerson(
            person_id=uuid.UUID(person_id),
            clan_id=seeded["clan_id"],
            actor=actor,
            changes=changes,
            expected_version=expected_version,
        )

    return _make


@pytest.fixture()
async def person_handler_two_sessions(
    session_factory: async_sessionmaker[AsyncSession],
    person_id: str,
) -> AsyncGenerator[tuple[PersonCommandHandler, PersonCommandHandler, int]]:
    """Two INDEPENDENT sessions/handlers, mirroring the two-sessionmaker pattern in
    test_claim_approval.py, so the race is genuine (not two handlers sharing one
    session's identity map)."""
    async with session_factory() as verify:
        current_version = await verify.scalar(
            sa.text("SELECT version FROM persons WHERE id = :id"), {"id": uuid.UUID(person_id)}
        )

    session_a = session_factory()
    session_b = session_factory()
    try:
        uow_a = SqlAlchemyUnitOfWork(session_a, create_event_dispatcher(session_a))
        uow_b = SqlAlchemyUnitOfWork(session_b, create_event_dispatcher(session_b))
        handler_a = PersonCommandHandler(SqlAlchemyPersonRepository(uow_a), uow_a)
        handler_b = PersonCommandHandler(SqlAlchemyPersonRepository(uow_b), uow_b)
        yield handler_a, handler_b, current_version
    finally:
        await session_a.close()
        await session_b.close()


# ── Tests ───────────────────────────────────────────────────────────────────


async def test_patch_without_expected_version_is_422(
    client: AsyncClient, editor_headers: dict[str, str], person_id: str
) -> None:
    resp = await client.patch(
        f"/api/v1/persons/{person_id}",
        json={"occupation": "Nông dân"},
        headers=editor_headers,
    )
    assert resp.status_code == 422


async def test_fresh_patch_increments_and_echoes_version(
    client: AsyncClient, editor_headers: dict[str, str], person_id: str
) -> None:
    get1 = await client.get(f"/api/v1/persons/{person_id}", headers=editor_headers)
    v = get1.json()["data"]["version"]
    resp = await client.patch(
        f"/api/v1/persons/{person_id}",
        json={"occupation": "Quan triều Nguyễn", "expected_version": v},
        headers=editor_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["version"] == v + 1


async def test_stale_patch_is_409_stale_write_and_loses_nothing(
    client: AsyncClient, editor_headers: dict[str, str], person_id: str
) -> None:
    get1 = await client.get(f"/api/v1/persons/{person_id}", headers=editor_headers)
    v = get1.json()["data"]["version"]
    # Editor A wins:
    ok = await client.patch(
        f"/api/v1/persons/{person_id}",
        json={"biography": "Tiểu sử hai trang", "expected_version": v},
        headers=editor_headers,
    )
    assert ok.status_code == 200, ok.text
    # Editor B (still holding v) loses with 409, and A's field survives:
    stale = await client.patch(
        f"/api/v1/persons/{person_id}",
        json={"occupation": "Thợ rèn", "expected_version": v},
        headers=editor_headers,
    )
    assert stale.status_code == 409
    body = stale.json()["error"]
    assert body["code"] == "stale_write"
    assert body["detail"]["current_version"] == v + 1
    after = await client.get(f"/api/v1/persons/{person_id}", headers=editor_headers)
    assert after.json()["data"]["biography"] == "Tiểu sử hai trang"


async def test_true_concurrent_patches_one_wins(
    person_handler_two_sessions: tuple[PersonCommandHandler, PersonCommandHandler, int],
    person_id: str,
    make_update: Callable[[str, dict[str, Any], int], UpdatePerson],
) -> None:
    """Two INDEPENDENT sessions/handlers race the same expected_version.

    Exactly one succeeds; the other raises ConflictError('stale_write').
    """
    handler_a, handler_b, current_version = person_handler_two_sessions
    results = await asyncio.gather(
        handler_a.update(make_update(person_id, {"biography": "A"}, current_version)),
        handler_b.update(make_update(person_id, {"occupation": "B"}, current_version)),
        return_exceptions=True,
    )
    failures = [r for r in results if isinstance(r, BaseException)]
    assert len(failures) == 1
    assert getattr(failures[0], "code", "") == "stale_write"


async def test_soft_delete_also_bumps_version(
    client: AsyncClient,
    admin_headers: dict[str, str],
    editor_headers: dict[str, str],
    person_id: str,
) -> None:
    get1 = await client.get(f"/api/v1/persons/{person_id}", headers=editor_headers)
    v = get1.json()["data"]["version"]
    del_resp = await client.delete(f"/api/v1/persons/{person_id}", headers=admin_headers)
    assert del_resp.status_code == 200, del_resp.text
    restore_resp = await client.post(f"/api/v1/persons/{person_id}/restore", headers=admin_headers)
    assert restore_resp.status_code == 200, restore_resp.text
    stale = await client.patch(
        f"/api/v1/persons/{person_id}",
        json={"notes": "x", "expected_version": v},
        headers=editor_headers,
    )
    assert stale.status_code == 409  # delete+restore bumped version twice
