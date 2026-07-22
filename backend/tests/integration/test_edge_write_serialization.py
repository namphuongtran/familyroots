"""Migration 022 (ADR-025): per-clan edge-write serialization + invariant-matching uniques.

H2 (review 2026-07-18): the 021 trigger serializes writers via FOR UPDATE on the two
ENDPOINT persons only — two concurrent edge inserts with disjoint endpoints never
serialize, so both cycle walks run on pre-race snapshots and a committed ancestry
cycle results. 022 adds a per-clan pg_advisory_xact_lock inside the trigger.

M2a/M2b: idx_marriages_unique_pair was partial on status='married' while the app's
"active" means status<>'divorced' (concurrent widowed same-pair creates both landed);
idx_parent_child_unique_edge keyed on relationship_type while the app forbids ANY
second live link per pair. 022 widens both to match the invariant (this also closes
tracked race M4 — a divorced→active UPDATE re-checks the widened index).

Raw SQL throughout (the app validator layer is tested elsewhere; these tests pin the
DATABASE's own guarantees). RED before 022: the race tests observe both writers
committing (corrupt state); the sabotage tests observe forbidden values landing.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError
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
            {"id": clan_id, "sg": f"ews-{clan_id.hex[:8]}"},
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


_INSERT_MARRIAGE = sa.text(
    "INSERT INTO marriages "
    "(id, person1_id, person2_id, created_by_clan_id, status, created_by) "
    "VALUES (:id, :p1, :p2, :cl, :st, :cb)"
)


def _marriage_params(p1: uuid.UUID, p2: uuid.UUID, clan: uuid.UUID, status: str) -> dict[str, Any]:
    return {"id": uuid.uuid4(), "p1": p1, "p2": p2, "cl": clan, "st": status, "cb": uuid.uuid4()}


_CYCLE_QUERY = sa.text(
    """
    WITH RECURSIVE r(start_id, node_id) AS (
        SELECT pc.child_id, pc.parent_id FROM parent_child pc
        WHERE pc.is_deleted = false AND pc.created_by_clan_id = :clan
        UNION
        SELECT r.start_id, pc.parent_id
        FROM parent_child pc JOIN r ON pc.child_id = r.node_id
        WHERE pc.is_deleted = false AND pc.created_by_clan_id = :clan
    )
    SELECT COUNT(*) FROM r WHERE node_id = start_id
    """
)


async def _race(
    maker: async_sessionmaker[AsyncSession],
    stmt: sa.TextClause,
    params_a: dict[str, Any],
    params_b: dict[str, Any],
) -> list[str]:
    """Run two INSERTs in concurrent transactions released by one gate."""

    async def _run(params: dict[str, Any], gate: asyncio.Event) -> str:
        async with maker() as s:
            await gate.wait()
            try:
                await s.execute(stmt, params)
                await s.commit()
                return "ok"
            except (DBAPIError, IntegrityError):
                await s.rollback()
                return "rejected"

    gate = asyncio.Event()
    t1 = asyncio.create_task(_run(params_a, gate))
    t2 = asyncio.create_task(_run(params_b, gate))
    gate.set()
    return sorted(await asyncio.gather(t1, t2))


async def _race_forced_overlap(
    maker: async_sessionmaker[AsyncSession],
    stmt: sa.TextClause,
    params_a: dict[str, Any],
    params_b: dict[str, Any],
) -> list[str]:
    """Like `_race`, but forces genuine transaction overlap.

    Only H2's disjoint-endpoint race needs this: with no real DB-level lock
    contention between the two writers, `_race`'s wall-clock gate alone doesn't
    guarantee overlap — a pooled connection left warm from setup lets one side's
    execute()+commit() finish before the other ever reaches the wire, so the
    second writer's snapshot legitimately (and misleadingly) already includes the
    first writer's committed row. Disposing the pool first (so neither side
    inherits a setup connection), pre-warming both connections identically, and
    rendezvousing on a barrier immediately before the statement removes that
    artifact.

    Do NOT reuse this for M2a/M2b: when both writers target the *same* two
    person rows (not disjoint), forcing this level of overlap collides with
    parent_child's FK-driven FOR KEY SHARE locks and the 021 trigger's FOR
    UPDATE upgrade, producing a genuine Postgres deadlock instead of the
    business-rule rejection those tests are pinning.
    """
    engine = maker.kw["bind"]
    await engine.dispose()  # drop any pooled connection from setup — start symmetric

    async def _run(params: dict[str, Any], gate: asyncio.Event, barrier: asyncio.Barrier) -> str:
        async with maker() as s:
            await s.execute(sa.text("SELECT 1"))  # pay connection setup before the gate
            await gate.wait()
            await barrier.wait()
            try:
                await s.execute(stmt, params)
                await s.commit()
                return "ok"
            except (DBAPIError, IntegrityError):
                await s.rollback()
                return "rejected"

    gate = asyncio.Event()
    barrier = asyncio.Barrier(2)
    t1 = asyncio.create_task(_run(params_a, gate, barrier))
    t2 = asyncio.create_task(_run(params_b, gate, barrier))
    gate.set()
    return sorted(await asyncio.gather(t1, t2))


# ── H2: disjoint-endpoint cycle race ───────────────────────────────────────────


async def test_disjoint_endpoint_cycle_race_loses_exactly_one(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    """The race the person-row locks CANNOT close: committed D→A and B→C; two
    transactions concurrently insert A→B and C→D. Their endpoint lock sets are
    disjoint ({A,B} vs {C,D}), so before 022 BOTH commit and the graph holds the
    cycle A→B→C→D→A. The per-clan advisory lock must serialize them: exactly one
    wins, and no cycle exists afterward."""
    clan, (a, b, c, d) = await _seed_persons(maker, 4)
    async with maker() as s:
        await s.execute(_INSERT_EDGE, _edge_params(d, a, clan))
        await s.execute(_INSERT_EDGE, _edge_params(b, c, clan))
        await s.commit()

    results = await _race_forced_overlap(
        maker, _INSERT_EDGE, _edge_params(a, b, clan), _edge_params(c, d, clan)
    )
    assert results == ["ok", "rejected"], f"both writers finished with {results}"

    async with maker() as s:
        cycles = (await s.execute(_CYCLE_QUERY, {"clan": clan})).scalar_one()
    assert cycles == 0, "a committed ancestry cycle exists — the DB let the race through"


async def test_disjoint_non_cycle_edges_both_succeed(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    """Negative control: the clan lock serializes but must NOT over-reject — two
    concurrent edges that do not close a cycle both commit."""
    clan, (p1, p2, p3, p4) = await _seed_persons(maker, 4)
    results = await _race(
        maker, _INSERT_EDGE, _edge_params(p1, p2, clan), _edge_params(p3, p4, clan)
    )
    assert results == ["ok", "ok"]


# ── M2a: marriage-pair uniqueness must match the app's "active" invariant ─────


async def test_concurrent_widowed_same_pair_marriages_lose_exactly_one(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    """has_active_marriage treats widowed as active, but the pre-022 unique index
    was partial on status='married' — two concurrent widowed inserts for the same
    pair both landed. The widened index must reject one."""
    clan, (h, w) = await _seed_persons(maker, 2)
    results = await _race(
        maker,
        _INSERT_MARRIAGE,
        _marriage_params(h, w, clan, "widowed"),
        _marriage_params(w, h, clan, "widowed"),  # opposite orientation too
    )
    assert results == ["ok", "rejected"], f"duplicate live marriages committed: {results}"


async def test_remarriage_after_divorce_still_allowed(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    """Divorced rows leave the partial index — the same pair can remarry."""
    clan, (h, w) = await _seed_persons(maker, 2)
    async with maker() as s:
        await s.execute(_INSERT_MARRIAGE, _marriage_params(h, w, clan, "divorced"))
        await s.commit()
    async with maker() as s:
        await s.execute(_INSERT_MARRIAGE, _marriage_params(h, w, clan, "married"))
        await s.commit()  # must not raise


async def test_second_live_marriage_same_pair_rejected_sequentially(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    """Plain (non-race) guard: separated + married same pair violates the widened
    index even without concurrency."""
    clan, (h, w) = await _seed_persons(maker, 2)
    async with maker() as s:
        await s.execute(_INSERT_MARRIAGE, _marriage_params(h, w, clan, "separated"))
        await s.commit()
    async with maker() as s:
        with pytest.raises((DBAPIError, IntegrityError)):
            await s.execute(_INSERT_MARRIAGE, _marriage_params(h, w, clan, "married"))
            await s.commit()


# ── M2b: one live edge per (clan, parent, child), any relationship_type ───────


async def test_concurrent_bio_and_step_edge_same_pair_lose_exactly_one(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    """The app forbids ANY second live link per pair, but the pre-022 index keyed
    on relationship_type — concurrent biological+step for the same (parent, child)
    both landed. The widened index must reject one."""
    clan, (p, ch) = await _seed_persons(maker, 2)
    results = await _race(
        maker,
        _INSERT_EDGE,
        _edge_params(p, ch, clan, rt="biological"),
        _edge_params(p, ch, clan, rt="step"),
    )
    assert results == ["ok", "rejected"], f"duplicate live edges committed: {results}"


# ── CHECK constraints (sabotage: forbidden values must not land) ──────────────


async def test_precision_check_rejects_unknown_value(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    """The five *_precision columns are Pydantic-validated only before 022 — a raw
    write could store 'approx' (the retired pre-HistoricalDate value). The CHECK
    must reject it on every column."""
    _clan, (p,) = await _seed_persons(maker, 1)
    async with maker() as s:
        with pytest.raises((DBAPIError, IntegrityError), match="ck_persons_birth_precision"):
            await s.execute(
                sa.text("UPDATE persons SET birth_date_precision = 'approx' WHERE id = :p"),
                {"p": p},
            )
            await s.commit()


async def test_branch_self_parent_rejected(maker: async_sessionmaker[AsyncSession]) -> None:
    clan, _ = await _seed_persons(maker, 1)
    branch_id = uuid.uuid4()
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO branches (id, clan_id, name) VALUES (:b, :c, 'Chi 1')"),
            {"b": branch_id, "c": clan},
        )
        await s.commit()
    async with maker() as s:
        with pytest.raises((DBAPIError, IntegrityError), match="ck_branches_no_self_parent"):
            await s.execute(
                sa.text("UPDATE branches SET parent_branch_id = :b WHERE id = :b"),
                {"b": branch_id},
            )
            await s.commit()
