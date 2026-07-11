"""Real-DB tests for the tree focus data API (get_ancestors dedup, enrichment, handler)."""

from __future__ import annotations

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


async def _clan(s: AsyncSession) -> uuid.UUID:
    cid = uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": cid, "s": f"c{cid.hex[:8]}"},
    )
    return cid


async def _person(
    s: AsyncSession, clan_id: uuid.UUID, creator: uuid.UUID, name: str = "P"
) -> uuid.UUID:
    pid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, :n, 'male', :c, :cb)"
        ),
        {"id": pid, "n": name, "c": clan_id, "cb": creator},
    )
    return pid


async def _member(
    s: AsyncSession,
    person_id: uuid.UUID,
    clan_id: uuid.UUID,
    *,
    is_founder: bool = False,
    branch_id: uuid.UUID | None = None,
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO clan_memberships (person_id, clan_id, is_founder, branch_id) "
            "VALUES (:p, :c, :f, :b)"
        ),
        {"p": person_id, "c": clan_id, "f": is_founder, "b": branch_id},
    )


async def _pc(
    s: AsyncSession,
    parent: uuid.UUID,
    child: uuid.UUID,
    clan_id: uuid.UUID,
    creator: uuid.UUID,
    *,
    birth_order: int | None = None,
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO parent_child "
            "(id, parent_id, child_id, created_by_clan_id, relationship_type, birth_order, "
            " created_by) "
            "VALUES (:id, :p, :c, :cl, 'biological', :bo, :cb)"
        ),
        {
            "id": uuid.uuid4(),
            "p": parent,
            "c": child,
            "cl": clan_id,
            "bo": birth_order,
            "cb": creator,
        },
    )


async def test_get_ancestors_no_duplicates_on_fan_out(async_session: AsyncSession) -> None:
    """A child with TWO parents must not duplicate shared grandparents in the ancestor list."""
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    gp = await _person(async_session, clan_id, creator, "GP")  # shared grandparent
    dad = await _person(async_session, clan_id, creator, "Dad")
    mom = await _person(async_session, clan_id, creator, "Mom")
    child = await _person(async_session, clan_id, creator, "Child")
    for p in (gp, dad, mom, child):
        await _member(async_session, p, clan_id)
    # gp is the parent of BOTH dad and mom → fan-out at the grandparent level.
    await _pc(async_session, gp, dad, clan_id, creator)
    await _pc(async_session, gp, mom, clan_id, creator)
    await _pc(async_session, dad, child, clan_id, creator)
    await _pc(async_session, mom, child, clan_id, creator)
    await async_session.commit()

    ancestors = await SqlAlchemyTreeRepository(async_session).get_ancestors(child, clan_id)

    ids = [a["id"] for a in ancestors]
    assert len(ids) == len(set(ids)), ids  # the old inline SQL fanned gp out twice
    assert str(gp) in ids and str(child) in ids
    # shape preserved: no child_id key leaked into the public /tree/ancestors output
    assert "child_id" not in ancestors[0]
