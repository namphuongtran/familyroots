"""find_relationship_path must not enumerate all simple paths.

The 011 body expanded parent+child+spouse edges to depth 20 with only a
per-path cycle guard — no global visited set. Family graphs are full of
parallel edges and 3-cycles, so simple-path counts grow combinatorially:
a 15-hop chain where each adjacent pair is connected by THREE edges
(parent-child + a married marriage + a divorced one) materializes 3^15
≈ 14 million CTE rows for one lookup. Migration 019 rewrites the function
as a frontier BFS with a global visited set — O(V+E), same signature, same
deterministic lexicographic tie-break.

The pin: the pathological lookup completes within a 3s statement timeout
and still returns the correct shortest path.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_HOPS = 15


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed_parallel_edge_chain(s: AsyncSession) -> tuple[uuid.UUID, list[uuid.UUID]]:
    clan_id, creator = uuid.uuid4(), uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
        {"id": clan_id, "sg": f"p-{clan_id.hex[:8]}"},
    )
    ids: list[uuid.UUID] = []
    for i in range(_HOPS + 1):
        pid = uuid.uuid4()
        ids.append(pid)
        await s.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                "VALUES (:id, :n, 'male', :c, :cb)"
            ),
            {"id": pid, "n": f"P{i}", "c": clan_id, "cb": creator},
        )
    for a, b in itertools.pairwise(ids):
        await s.execute(
            sa.text(
                "INSERT INTO parent_child "
                "(id, parent_id, child_id, created_by_clan_id, relationship_type, created_by) "
                "VALUES (:id, :p, :c, :cl, 'biological', :cb)"
            ),
            {"id": uuid.uuid4(), "p": a, "c": b, "cl": clan_id, "cb": creator},
        )
        for status, order in (("married", 1), ("divorced", 2)):
            await s.execute(
                sa.text(
                    "INSERT INTO marriages (id, person1_id, person2_id, status, spouse_order, "
                    " created_by_clan_id, created_by) "
                    "VALUES (:id, :p1, :p2, :st, :o, :cl, :cb)"
                ),
                {
                    "id": uuid.uuid4(),
                    "p1": a,
                    "p2": b,
                    "st": status,
                    "o": order,
                    "cl": clan_id,
                    "cb": creator,
                },
            )
    await s.commit()
    return clan_id, ids


async def test_pathological_graph_resolves_within_timeout(async_session: AsyncSession) -> None:
    clan_id, ids = await _seed_parallel_edge_chain(async_session)
    await async_session.execute(sa.text("SET statement_timeout = '3s'"))
    rows = (
        await async_session.execute(
            sa.text(
                "SELECT step, person_id, edge_type "
                "FROM public.find_relationship_path(:f, :t, :c) ORDER BY step"
            ),
            {"f": ids[0], "t": ids[-1], "c": clan_id},
        )
    ).all()
    assert [r.person_id for r in rows] == ids  # the one shortest node path
    assert rows[0].edge_type is None
    # Deterministic tie-break across the 3 parallel edges per hop:
    # 'child' < 'spouse' lexicographically, so every hop resolves to 'child'.
    assert {r.edge_type for r in rows[1:]} == {"child"}
