"""Cross-clan edge prevention is an APPLICATION-LAYER guarantee (M10, ADR-031).

M10 accepted that no DB trigger backstops cross-clan edges; instead the relationship
write handlers call ``ensure_persons_in_clan`` (a ``clan_memberships`` membership check)
and reject an edge whose endpoint is not a member of the edge's clan with
``404 person_not_found``. This pins that guarantee TWO-SIDED over real HTTP, so a
regression that drops the guard fails loudly (the residual-risk boundary ADR-031
documents). The read-side symmetry is covered by ``test_relationship_isolation.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
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


async def _clan_with_editor(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, dict[str, str]]:
    """A clan + an approved editor; returns (clan_id, that editor's request headers)."""
    clan_id, editor_id = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sl)"),
            {"id": clan_id, "sl": f"c-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'E')"),
            {"id": editor_id, "e": f"{editor_id.hex[:8]}@ex.com"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles (user_id, clan_id, role, is_approved, "
                "approved_by, approved_at) VALUES (:u, :c, 'editor', true, :u, now())"
            ),
            {"u": editor_id, "c": clan_id},
        )
        await s.commit()
    return clan_id, {
        "Authorization": f"Bearer {editor_id}",
        "X-Current-Clan-Id": str(clan_id),
    }


async def _make_person(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    """Create a person via the API — POST /persons uses save_with_membership, so the
    person becomes a member of the current X-Current-Clan-Id clan."""
    resp = await client.post(
        "/api/v1/persons", headers=headers, json={"full_name": name, "gender": "male"}
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


async def test_parent_child_edge_to_foreign_clan_person_rejected(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Creating a parent-child edge in clan B whose parent is a clan-A-only person is
    rejected 404 person_not_found (the app-layer membership guard). Two-sided: the same
    person is usable inside its own clan A."""
    _clan_a, headers_a = await _clan_with_editor(session_factory)
    _clan_b, headers_b = await _clan_with_editor(session_factory)

    p_a = await _make_person(client, headers_a, "A-only Parent")  # member of A only
    child_b = await _make_person(client, headers_b, "B Child")  # member of B
    other_b = await _make_person(client, headers_b, "B Other")  # member of B

    # Clan B tries to make p_a (a clan-A person) a parent of a clan-B child → rejected.
    resp = await client.post(
        "/api/v1/relationships/parent-child",
        headers=headers_b,
        json={"parent_id": p_a, "child_id": child_b, "relationship_type": "biological"},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "person_not_found"

    # Control (guard doesn't over-reject): two clan-B members link fine.
    ok = await client.post(
        "/api/v1/relationships/parent-child",
        headers=headers_b,
        json={"parent_id": other_b, "child_id": child_b, "relationship_type": "biological"},
    )
    assert ok.status_code == 201, ok.text

    # Two-sided: p_a IS usable within clan A (a second A person as its child).
    child_a = await _make_person(client, headers_a, "A Child")
    ok_a = await client.post(
        "/api/v1/relationships/parent-child",
        headers=headers_a,
        json={"parent_id": p_a, "child_id": child_a, "relationship_type": "biological"},
    )
    assert ok_a.status_code == 201, ok_a.text


async def test_marriage_edge_to_foreign_clan_person_rejected(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A marriage in clan B between a clan-A person and a clan-B person is rejected
    404 person_not_found; a same-clan marriage succeeds."""
    _clan_a, headers_a = await _clan_with_editor(session_factory)
    _clan_b, headers_b = await _clan_with_editor(session_factory)

    p_a = await _make_person(client, headers_a, "A Spouse")  # member of A only
    p_b1 = await _make_person(client, headers_b, "B Spouse 1")
    p_b2 = await _make_person(client, headers_b, "B Spouse 2")

    resp = await client.post(
        "/api/v1/relationships/marriages",
        headers=headers_b,
        json={"person1_id": p_b1, "person2_id": p_a},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "person_not_found"

    ok = await client.post(
        "/api/v1/relationships/marriages",
        headers=headers_b,
        json={"person1_id": p_b1, "person2_id": p_b2},
    )
    assert ok.status_code == 201, ok.text
