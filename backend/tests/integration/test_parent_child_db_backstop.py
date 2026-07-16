"""DB backstop for genealogy graph invariants (ADR-023, migration 021).

Max-2-biological-parents and acyclicity were application-layer
SELECT-then-INSERT pre-checks only: under READ COMMITTED, two editors
concurrently adding different "biological fathers" both pass the pre-check
and both commit (child ends with 3 bio parents); concurrent A→B and B→A
inserts commit a cycle. spouse_order got a DB backstop in migration 015 —
these did not.

Migration 021 adds a trigger on parent_child that locks both endpoint
person rows (deterministic order) to serialize concurrent writers, then
re-checks both invariants against committed state. These tests exercise the
trigger directly with raw SQL (bypassing the app validator — that layer is
already tested) including a genuine two-transaction race.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.fixture()
async def maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_persons(
    maker: async_sessionmaker[AsyncSession], count: int
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    clan_id, creator = uuid.uuid4(), uuid.uuid4()
    ids = [uuid.uuid4() for _ in range(count)]
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"bs-{clan_id.hex[:8]}"},
        )
        for i, pid in enumerate(ids):
            await s.execute(
                sa.text(
                    "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                    "VALUES (:id, :n, 'male', :c, :cb)"
                ),
                {"id": pid, "n": f"P{i}", "c": clan_id, "cb": creator},
            )
        await s.commit()
    return clan_id, ids


_INSERT_EDGE = sa.text(
    "INSERT INTO parent_child "
    "(id, parent_id, child_id, created_by_clan_id, relationship_type, created_by) "
    "VALUES (:id, :p, :c, :cl, :rt, :cb)"
)


def _edge_params(
    parent: uuid.UUID, child: uuid.UUID, clan: uuid.UUID, rt: str = "biological"
) -> dict[str, Any]:
    return {"id": uuid.uuid4(), "p": parent, "c": child, "cl": clan, "rt": rt, "cb": uuid.uuid4()}


async def test_third_biological_parent_rejected(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    clan, (p1, p2, p3, child) = await _seed_persons(maker, 4)
    async with maker() as s:
        await s.execute(_INSERT_EDGE, _edge_params(p1, child, clan))
        await s.execute(_INSERT_EDGE, _edge_params(p2, child, clan))
        await s.commit()
    async with maker() as s:
        with pytest.raises(DBAPIError, match="too_many_biological_parents"):
            await s.execute(_INSERT_EDGE, _edge_params(p3, child, clan))
            await s.commit()


async def test_third_adoptive_parent_allowed(maker: async_sessionmaker[AsyncSession]) -> None:
    """The cap is biological-only — adoptive/step edges are unlimited."""
    clan, (p1, p2, p3, child) = await _seed_persons(maker, 4)
    async with maker() as s:
        await s.execute(_INSERT_EDGE, _edge_params(p1, child, clan))
        await s.execute(_INSERT_EDGE, _edge_params(p2, child, clan))
        await s.execute(_INSERT_EDGE, _edge_params(p3, child, clan, rt="adopted"))
        await s.commit()  # must not raise


async def test_cycle_rejected(maker: async_sessionmaker[AsyncSession]) -> None:
    clan, (a, b, c) = await _seed_persons(maker, 3)
    async with maker() as s:
        await s.execute(_INSERT_EDGE, _edge_params(a, b, clan))
        await s.execute(_INSERT_EDGE, _edge_params(b, c, clan))
        await s.commit()
    async with maker() as s:
        with pytest.raises(DBAPIError, match="relationship_cycle"):
            await s.execute(_INSERT_EDGE, _edge_params(c, a, clan))  # closes a→b→c→a
            await s.commit()


async def test_self_edge_rejected(maker: async_sessionmaker[AsyncSession]) -> None:
    # The baseline CHECK (ck_..._no_self) fires before the trigger; the trigger
    # keeps its own guard as defense should that constraint ever be dropped.
    clan, (a,) = await _seed_persons(maker, 1)
    async with maker() as s:
        with pytest.raises(DBAPIError, match=r"no_self|relationship_cycle"):
            await s.execute(_INSERT_EDGE, _edge_params(a, a, clan))
            await s.commit()


async def test_concurrent_bio_parent_race_loses_exactly_one(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    """The exact race the app pre-check cannot stop: the child already has one
    bio parent; two transactions concurrently add a different second-and-third
    bio parent. The trigger's person-row lock serializes them — the first
    commit wins (2 parents), the second must fail."""
    clan, (p1, p2, p3, child) = await _seed_persons(maker, 4)
    async with maker() as s:
        await s.execute(_INSERT_EDGE, _edge_params(p1, child, clan))
        await s.commit()

    async def _insert(parent: uuid.UUID, start_gate: asyncio.Event) -> str:
        async with maker() as s:
            await start_gate.wait()
            try:
                await s.execute(_INSERT_EDGE, _edge_params(parent, child, clan))
                await s.commit()
                return "ok"
            except DBAPIError:
                await s.rollback()
                return "rejected"

    gate = asyncio.Event()
    t1 = asyncio.create_task(_insert(p2, gate))
    t2 = asyncio.create_task(_insert(p3, gate))
    gate.set()
    results = sorted(await asyncio.gather(t1, t2))

    assert results == ["ok", "rejected"], results
    async with maker() as s:
        count = await s.scalar(
            sa.text(
                "SELECT COUNT(*) FROM parent_child WHERE child_id = :c "
                "AND relationship_type = 'biological' AND is_deleted = false"
            ),
            {"c": child},
        )
    assert count == 2  # never 3
