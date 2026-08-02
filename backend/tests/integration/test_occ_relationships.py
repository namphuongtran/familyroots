"""Optimistic concurrency on marriage + parent-child PATCH (H1).

Real Postgres (migrated_db_url), real RBAC (require_role queries user_clan_roles),
real Relationship aggregates + repositories. Only JWT *verification* is stubbed —
the Authorization header carries the user id directly instead of a signed token, so
these tests focus on the OCC contract rather than re-proving auth (already covered
by test_auth_http_flow.py). Mirrors tests/integration/test_occ_persons.py.
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
    """A clan plus an approved editor membership."""
    clan_id = uuid.uuid4()
    editor_id = uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'OCC Rel Clan', :slug)"),
            {"id": clan_id, "slug": f"occrel-{clan_id.hex[:8]}"},
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
async def two_person_ids(client: AsyncClient, editor_headers: dict[str, str]) -> tuple[str, str]:
    ids = []
    for name, gender in (("Ông Occ", "male"), ("Bà Occ", "female")):
        resp = await client.post(
            "/api/v1/persons",
            headers=editor_headers,
            json={"full_name": name, "gender": gender},
        )
        assert resp.status_code == 201, resp.text
        ids.append(str(resp.json()["data"]["id"]))
    return ids[0], ids[1]


@pytest.fixture()
async def marriage_id(
    client: AsyncClient, editor_headers: dict[str, str], two_person_ids: tuple[str, str]
) -> str:
    p1, p2 = two_person_ids
    resp = await client.post(
        "/api/v1/relationships/marriages",
        headers=editor_headers,
        json={"person1_id": p1, "person2_id": p2},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["version"] == 1
    return str(resp.json()["data"]["id"])


@pytest.fixture()
async def parent_child_id(
    client: AsyncClient, editor_headers: dict[str, str], two_person_ids: tuple[str, str]
) -> str:
    parent, child = two_person_ids
    resp = await client.post(
        "/api/v1/relationships/parent-child",
        headers=editor_headers,
        json={"parent_id": parent, "child_id": child, "birth_order": 1},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["version"] == 1
    return str(resp.json()["data"]["id"])


# ── Tests ───────────────────────────────────────────────────────────────────


async def test_marriage_patch_without_expected_version_is_422(
    client: AsyncClient, editor_headers: dict[str, str], marriage_id: str
) -> None:
    resp = await client.patch(
        f"/api/v1/relationships/marriages/{marriage_id}",
        json={"notes": "x"},
        headers=editor_headers,
    )
    assert resp.status_code == 422


async def test_marriage_fresh_patch_increments_version(
    client: AsyncClient, editor_headers: dict[str, str], marriage_id: str
) -> None:
    get1 = await client.get(
        f"/api/v1/relationships/marriages/{marriage_id}", headers=editor_headers
    )
    v = get1.json()["data"]["version"]
    resp = await client.patch(
        f"/api/v1/relationships/marriages/{marriage_id}",
        json={"marriage_place": "Huế", "expected_version": v},
        headers=editor_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["version"] == v + 1


async def test_marriage_stale_patch_is_409(
    client: AsyncClient, editor_headers: dict[str, str], marriage_id: str
) -> None:
    get1 = await client.get(
        f"/api/v1/relationships/marriages/{marriage_id}", headers=editor_headers
    )
    v = get1.json()["data"]["version"]
    ok = await client.patch(
        f"/api/v1/relationships/marriages/{marriage_id}",
        json={"notes": "first", "expected_version": v},
        headers=editor_headers,
    )
    assert ok.status_code == 200, ok.text
    stale = await client.patch(
        f"/api/v1/relationships/marriages/{marriage_id}",
        json={"notes": "second", "expected_version": v},
        headers=editor_headers,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_write"
    assert stale.json()["error"]["detail"]["current_version"] == v + 1


async def test_parent_child_full_occ_cycle(
    client: AsyncClient, editor_headers: dict[str, str], parent_child_id: str
) -> None:
    # 422 missing version
    r0 = await client.patch(
        f"/api/v1/relationships/parent-child/{parent_child_id}",
        json={"notes": "x"},
        headers=editor_headers,
    )
    assert r0.status_code == 422
    # fresh increments
    get1 = await client.get(
        f"/api/v1/relationships/parent-child/{parent_child_id}", headers=editor_headers
    )
    v = get1.json()["data"]["version"]
    r1 = await client.patch(
        f"/api/v1/relationships/parent-child/{parent_child_id}",
        json={"birth_order": 2, "expected_version": v},
        headers=editor_headers,
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["data"]["version"] == v + 1
    # stale 409
    r2 = await client.patch(
        f"/api/v1/relationships/parent-child/{parent_child_id}",
        json={"birth_order": 3, "expected_version": v},
        headers=editor_headers,
    )
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "stale_write"
