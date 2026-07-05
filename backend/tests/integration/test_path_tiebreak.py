"""find_relationship_path must return ONE coherent shortest path when several tie.

Full siblings who share TWO parents (X and Y) have two equal-length shortest paths
A→X→B and A→Y→B. The pre-011 function interleaved both and sliced a corrupted mix
(source duplicated, target dropped). Migration 011 selects one whole path; a revert to
the old body fails these assertions.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence.tree_repository import SqlAlchemyTreeRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _person(s: AsyncSession, clan_id: uuid.UUID, creator: uuid.UUID) -> uuid.UUID:
    pid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, 'P', 'male', :c, :cb)"
        ),
        {"id": pid, "c": clan_id, "cb": creator},
    )
    return pid


async def _parent_child(
    s: AsyncSession, parent: uuid.UUID, child: uuid.UUID, clan_id: uuid.UUID, creator: uuid.UUID
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO parent_child "
            "(id, parent_id, child_id, created_by_clan_id, relationship_type, created_by) "
            "VALUES (:id, :p, :c, :cl, 'biological', :cb)"
        ),
        {"id": uuid.uuid4(), "p": parent, "c": child, "cl": clan_id, "cb": creator},
    )


async def test_two_tied_shortest_paths_return_one_coherent_path(
    async_session: AsyncSession,
) -> None:
    clan_id, creator = uuid.uuid4(), uuid.uuid4()
    await async_session.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:8]}"},
    )
    a = await _person(async_session, clan_id, creator)
    b = await _person(async_session, clan_id, creator)
    x = await _person(async_session, clan_id, creator)
    y = await _person(async_session, clan_id, creator)
    # A and B are full siblings sharing BOTH parents X and Y → two shortest paths.
    for parent in (x, y):
        await _parent_child(async_session, parent, a, clan_id, creator)
        await _parent_child(async_session, parent, b, clan_id, creator)
    await async_session.commit()

    path = await SqlAlchemyTreeRepository(async_session).find_path(a, b, clan_id)

    ids = [step["person_id"] for step in path]
    edges = [step["edge_type"] for step in path]
    # ONE coherent A → (shared parent) → B path, not an interleaved/corrupted mix.
    assert len(path) == 3, path
    assert ids[0] == str(a) and ids[-1] == str(b), ids
    assert ids[1] in {str(x), str(y)}, ids
    assert len(set(ids)) == 3, ids  # no duplicated node (the old bug duplicated A)
    assert edges == [None, "parent", "child"], edges


async def test_unreachable_target_returns_empty(async_session: AsyncSession) -> None:
    """No path (winner CTE empty) → empty result → handler reports not-found."""
    clan_id, creator = uuid.uuid4(), uuid.uuid4()
    await async_session.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:8]}"},
    )
    a = await _person(async_session, clan_id, creator)
    b = await _person(async_session, clan_id, creator)  # no edges between a and b
    await async_session.commit()

    path = await SqlAlchemyTreeRepository(async_session).find_path(a, b, clan_id)
    assert path == []
