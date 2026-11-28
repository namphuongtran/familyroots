"""``PATCH /branches/{id}`` refuses a parent whose ancestor chain contains the branch.

Reading: the request is sent and the response read, then the row is re-read. Pass reading
is (422 ``branch_parent_cycle``, parent still null); the unguarded reading is (200, parent B).
Real Postgres, real handlers, real RBAC; only JWT verification is stubbed.
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

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None
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
    clan_id, admin_id = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, slug, name) VALUES (:id, :slug, 'Họ Chu kỳ')"),
            {"id": clan_id, "slug": f"bc-{clan_id.hex[:10]}"},
        )
        await s.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'qt')"),
            {"id": admin_id, "e": f"{admin_id.hex[:10]}@example.com"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:uid, :cid, 'admin', true, :uid, now())"
            ),
            {"uid": admin_id, "cid": clan_id},
        )
        await s.commit()
    return {"clan_id": clan_id, "admin_id": admin_id}


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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


def _h(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['admin_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


async def _create(client: AsyncClient, seeded: dict[str, Any], name: str, parent: Any) -> str:
    body: dict[str, Any] = {"name": name}
    if parent:
        body["parent_branch_id"] = parent
    r = await client.post("/api/v1/branches", json=body, headers=_h(seeded))
    assert r.status_code == 201, r.text
    return str(r.json()["data"]["id"])


async def _parent(sf: async_sessionmaker[AsyncSession], branch_id: str) -> Any:
    async with sf() as s:
        return (
            await s.execute(
                sa.text("SELECT parent_branch_id FROM branches WHERE id = :id"),
                {"id": uuid.UUID(branch_id)},
            )
        ).scalar_one()


async def test_two_step_cycle_is_refused_and_row_unchanged(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, Any]
) -> None:
    a = await _create(client, seeded, "A", None)
    b = await _create(client, seeded, "B", a)

    r = await client.patch(
        f"/api/v1/branches/{a}", json={"parent_branch_id": b}, headers=_h(seeded)
    )

    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "branch_parent_cycle"
    assert await _parent(session_factory, a) is None


async def test_three_step_cycle_is_refused_and_row_unchanged(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, Any]
) -> None:
    a = await _create(client, seeded, "A", None)
    b = await _create(client, seeded, "B", a)
    c = await _create(client, seeded, "C", b)

    r = await client.patch(
        f"/api/v1/branches/{a}", json={"parent_branch_id": c}, headers=_h(seeded)
    )

    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "branch_parent_cycle"
    assert await _parent(session_factory, a) is None


async def test_self_parent_clear_and_non_ancestor_move_still_work(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, Any]
) -> None:
    a = await _create(client, seeded, "A", None)
    b = await _create(client, seeded, "B", a)
    c = await _create(client, seeded, "C", None)

    r = await client.patch(
        f"/api/v1/branches/{a}", json={"parent_branch_id": a}, headers=_h(seeded)
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "branch_cannot_be_own_parent"

    r = await client.patch(
        f"/api/v1/branches/{b}", json={"parent_branch_id": c}, headers=_h(seeded)
    )
    assert r.status_code == 200, r.text
    assert await _parent(session_factory, b) == uuid.UUID(c)

    r = await client.patch(
        f"/api/v1/branches/{b}", json={"parent_branch_id": None}, headers=_h(seeded)
    )
    assert r.status_code == 200, r.text
    assert await _parent(session_factory, b) is None
