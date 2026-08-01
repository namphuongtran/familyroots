"""Track-B B3 (perf net): the full-tree read must not N+1 on clan size.

get_full_tree is the highest-traffic read and the most N+1-prone: it walks an entire
clan's descendants. tree_builder is deliberately written to bulk-fetch then assemble in
memory — compute_generation_map pulls all parent_child edges in ONE query, and
build_descendants_tree uses the get_family_tree_flat recursive CTE plus a single bulk
spouse query and a single mother-map query — so the number of SQL statements is a small
CONSTANT, independent of both clan size (node count) and tree depth (generations).

This pins that invariant: a small clan and a much larger/deeper clan must issue the SAME
number of statements. A refactor that reintroduces per-node or per-generation querying
(the classic tree N+1) scales the count and fails here.

Real Postgres; statements counted via a before_cursor_execute listener (same technique
as test_persons_batch_query_scaling.py).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.application.tree.handlers import TreeQueryHandler
from app.application.tree.queries import GetFullTree
from app.infrastructure.persistence.tree_repository import SqlAlchemyTreeRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


# ── seed helpers (mirror test_doi_authority.py) ───────────────────────────────


async def _clan(s: AsyncSession) -> uuid.UUID:
    cid = uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": cid, "s": f"c{cid.hex[:8]}"},
    )
    return cid


async def _person(s: AsyncSession, clan_id: uuid.UUID, creator: uuid.UUID, name: str) -> uuid.UUID:
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
    s: AsyncSession, person_id: uuid.UUID, clan_id: uuid.UUID, *, is_founder: bool = False
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO clan_memberships (person_id, clan_id, is_founder) VALUES (:p, :c, :f)"
        ),
        {"p": person_id, "c": clan_id, "f": is_founder},
    )


async def _pc(
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


async def _seed_tree(
    maker: async_sessionmaker[AsyncSession], *, generations: int, branching: int
) -> tuple[uuid.UUID, int]:
    """A founder + a `branching`-ary descendants tree of `generations` levels
    (founder is a member with is_founder=true). Returns (clan_id, person_count)."""
    creator = uuid.uuid4()
    async with maker() as s:
        clan_id = await _clan(s)
        founder = await _person(s, clan_id, creator, "F")
        await _member(s, founder, clan_id, is_founder=True)
        frontier = [founder]
        count = 1
        for gen in range(generations):
            nxt: list[uuid.UUID] = []
            for parent in frontier:
                for i in range(branching):
                    child = await _person(s, clan_id, creator, f"P{gen}-{i}-{uuid.uuid4().hex[:4]}")
                    await _member(s, child, clan_id)
                    await _pc(s, parent, child, clan_id, creator)
                    nxt.append(child)
                    count += 1
            frontier = nxt
        await s.commit()
    return clan_id, count


async def _full_tree_statement_count(
    engine: AsyncEngine, clan_id: uuid.UUID
) -> tuple[int, dict[str, Any]]:
    """Run get_full_tree on a fresh session, counting the SQL statements it issues."""
    statements: list[str] = []

    def _count(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        statements.append(statement)

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        handler = TreeQueryHandler(SqlAlchemyTreeRepository(session))
        sa.event.listen(engine.sync_engine, "before_cursor_execute", _count)
        try:
            result = await handler.get_full_tree(GetFullTree(clan_id=clan_id, max_generations=50))
        finally:
            sa.event.remove(engine.sync_engine, "before_cursor_execute", _count)
    return len(statements), result


async def test_full_tree_query_count_is_independent_of_clan_size(engine: AsyncEngine) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    small_clan, small_n = await _seed_tree(maker, generations=1, branching=2)  # 3 persons, depth 1
    large_clan, large_n = await _seed_tree(maker, generations=3, branching=2)  # 15 persons, depth 3

    small_count, small_tree = await _full_tree_statement_count(engine, small_clan)
    large_count, large_tree = await _full_tree_statement_count(engine, large_clan)

    # Sanity: the two trees are genuinely different in size and depth, so a constant
    # statement count is a meaningful result (not both trivially tiny).
    assert large_n > small_n * 3
    assert large_tree["total_persons"] == large_n
    assert large_tree["total_generations"] > small_tree["total_generations"]

    # The pin: same statement count regardless of node count OR depth (no N+1).
    assert large_count == small_count, (
        f"full-tree query count scales with the clan: {small_n} persons -> {small_count} "
        f"statements, {large_n} persons -> {large_count} statements"
    )
    # And it stays a small constant — a coarse guard against a gross regression.
    assert small_count <= 8, f"full-tree issues {small_count} statements for a 3-person clan"
