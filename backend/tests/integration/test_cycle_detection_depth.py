"""M1: cycle detection must work beyond 20 generations."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import create_app

pytestmark = pytest.mark.integration


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
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Cycle Depth Clan', :slug)"),
            {"id": clan_id, "slug": f"cycledepth-{clan_id.hex[:8]}"},
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
async def chain_25_generations(
    session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, Any]
) -> tuple[str, str]:
    """25 persons g[0] (thủy tổ) .. g[24], parent edges g[i]->g[i+1], all via raw SQL
    for speed. Birth dates 25 years apart (g[0] oldest) so the >=12y biological-parent
    age rule would pass if these edges were re-validated. Returns (top_id, bottom_id)."""
    clan_id = seeded["clan_id"]
    creator = seeded["editor_id"]
    ids = [uuid.uuid4() for _ in range(25)]
    async with session_factory() as s:
        for i, pid in enumerate(ids):
            birth = date(1398 + 25 * i, 1, 1)
            await s.execute(
                sa.text(
                    "INSERT INTO persons (id, full_name, gender, birth_date, "
                    "created_by_clan_id, created_by) "
                    "VALUES (:id, :n, 'unknown', :bd, :cid, :cb)"
                ),
                {"id": pid, "n": f"Gen {i}", "bd": birth, "cid": clan_id, "cb": creator},
            )
            await s.execute(
                sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
                {"p": pid, "c": clan_id},
            )
        for i in range(24):
            await s.execute(
                sa.text(
                    "INSERT INTO parent_child "
                    "(id, parent_id, child_id, created_by_clan_id, relationship_type, created_by) "
                    "VALUES (:id, :p, :c, :cid, 'biological', :cb)"
                ),
                {
                    "id": uuid.uuid4(),
                    "p": ids[i],
                    "c": ids[i + 1],
                    "cid": clan_id,
                    "cb": creator,
                },
            )
        await s.commit()
    return str(ids[0]), str(ids[24])


@pytest.fixture()
async def chain_25_generations_with_extra_person(
    session_factory: async_sessionmaker[AsyncSession],
    seeded: dict[str, Any],
    chain_25_generations: tuple[str, str],
) -> tuple[str, str]:
    """The same 25-generation chain, plus one unlinked extra person born well after
    g[24] (the chain's bottom) so a genuine biological edge at depth 25 validates."""
    _, bottom_id = chain_25_generations
    clan_id = seeded["clan_id"]
    creator = seeded["editor_id"]
    new_id = uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, birth_date, "
                "created_by_clan_id, created_by) "
                "VALUES (:id, 'Gen 25 Extra', 'unknown', :bd, :cid, :cb)"
            ),
            {"id": new_id, "bd": date(2018, 1, 1), "cid": clan_id, "cb": creator},
        )
        await s.execute(
            sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
            {"p": new_id, "c": clan_id},
        )
        await s.commit()
    return bottom_id, str(new_id)


async def test_cycle_across_25_generations_is_blocked(client, editor_headers, chain_25_generations):
    """chain_25_generations: persons g[0] (thủy tổ) .. g[24], parent edges g[i]->g[i+1].
    Adding 'g[24] is parent of g[0]' closes a 25-generation loop and must be rejected."""
    top_id, bottom_id = chain_25_generations
    resp = await client.post(
        "/api/v1/relationships/parent-child",
        json={"parent_id": bottom_id, "child_id": top_id, "relationship_type": "adopted"},
        headers=editor_headers,
    )
    assert resp.status_code in (400, 422)
    assert resp.json()["error"]["code"] == "relationship.creates_cycle"


async def test_normal_deep_edge_still_allowed(
    client, editor_headers, chain_25_generations_with_extra_person
):
    """A legitimate edge at depth 25 (new person as child of g[24]) still validates."""
    bottom_id, new_person_id = chain_25_generations_with_extra_person
    resp = await client.post(
        "/api/v1/relationships/parent-child",
        json={"parent_id": bottom_id, "child_id": new_person_id, "relationship_type": "biological"},
        headers=editor_headers,
    )
    assert resp.status_code == 201
