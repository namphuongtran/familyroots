# DB Integrity Backstops (A2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close H2 (disjoint-endpoint cycle race in the ADR-023 trigger), M2a/M2b (unique indexes narrower than the app invariants — also closes tracked M4), and the precision/branch CHECK gaps — one migration (022), RED-first race tests, ADR-025. Spec: `docs/superpowers/specs/2026-07-18-db-integrity-backstops-design.md`.

**Architecture:** Per-clan `pg_advisory_xact_lock(728116, hashtext(clan_id))` added to `parent_child_integrity_guard()`; `idx_marriages_unique_pair` widened to `status <> 'divorced' AND is_deleted = false` (status out of the key); `idx_parent_child_unique_edge` drops `relationship_type`; six CHECK constraints. No application-code changes — the app validator stays as the friendly pre-check, the DB is the backstop.

**Tech Stack:** Alembic (raw SQL migration, single linear chain, revision id ≤32 chars), plpgsql trigger, real-Postgres integration tests mirroring `tests/integration/test_parent_child_db_backstop.py`'s two-transaction gate harness.

## Global Constraints

- **No application code changes.** Only: one new migration, comment-only model updates, tests, docs/ADR.
- Migration id/filename: `022_edge_write_serialization` (≤32 chars — it is 28). Revises `021_parent_child_guard`.
- Same index names kept (`idx_marriages_unique_pair`, `idx_parent_child_unique_edge`). Error contract unchanged: 23505 → 409 `conflict` (generic handler), 23514 slugs `relationship_cycle` / `too_many_biological_parents` unchanged.
- Prechecks fail LOUDLY listing offending rows (pattern of migrations 015/021); never repair data. **No dedicated precheck tests** — house precedent (015/021 prechecks are untested migration-time operator guards; post-022 constraints make violating seeds impossible). This is a deliberate, documented deviation from spec test item 5.
- Downgrade must fully restore: the 021 function body (no advisory lock), the 007 index definitions, and drop all six CHECKs.
- RED-first: Task 1's tests must be run and their exact failures recorded BEFORE migration 022 exists.
- Full quality gate before claiming done: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.

---

### Task 1: RED race + sabotage tests for migration 022

**Files:**
- Create: `backend/tests/integration/test_edge_write_serialization.py`

**Interfaces:**
- Consumes: `migrated_db_url` session fixture (integration conftest); harness pattern from `tests/integration/test_parent_child_db_backstop.py` (engine/maker fixtures, `_seed_persons`, `asyncio.Event` gate).
- Produces: the executable specification for Task 2's migration — every test here must FAIL today and PASS after 022.

- [ ] **Step 1: Write the test file**

Create `backend/tests/integration/test_edge_write_serialization.py`:

```python
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


def _marriage_params(
    p1: uuid.UUID, p2: uuid.UUID, clan: uuid.UUID, status: str
) -> dict[str, Any]:
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

    results = await _race(
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
    clan, (p,) = await _seed_persons(maker, 1)
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
            sa.text(
                "INSERT INTO branches (id, clan_id, name) VALUES (:b, :c, 'Chi 1')"
            ),
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
```

If a raw INSERT above is missing a NOT NULL column (verify against `app/models/marriage.py`, `app/models/branch.py`, and migration `001_initial.py`), add the minimal missing columns to the INSERT — do not weaken any assertion.

- [ ] **Step 2: Run — record the RED failures (this is the sabotage evidence)**

Run: `cd backend && uv run pytest tests/integration/test_edge_write_serialization.py -v`
Expected BEFORE migration 022 exists:
- `test_disjoint_endpoint_cycle_race_loses_exactly_one` FAILS: `results == ["ok", "ok"]` and/or `cycles > 0` — the corruption is real.
- `test_concurrent_widowed_same_pair_marriages_lose_exactly_one` FAILS: both "ok".
- `test_concurrent_bio_and_step_edge_same_pair_lose_exactly_one` FAILS: both "ok".
- `test_second_live_marriage_same_pair_rejected_sequentially` FAILS: no exception raised.
- `test_precision_check_rejects_unknown_value` FAILS: no exception raised.
- `test_branch_self_parent_rejected` FAILS: no exception raised.
- `test_disjoint_non_cycle_edges_both_succeed` and `test_remarriage_after_divorce_still_allowed` PASS (controls).

- [ ] **Step 3: Commit the RED tests**

```bash
git add backend/tests/integration/test_edge_write_serialization.py
git commit -m "test: RED races + sabotage for edge-write serialization (H2, M2a, M2b, CHECKs)"
```

---

### Task 2: Migration `022_edge_write_serialization` + model comment updates

**Files:**
- Create: `backend/migrations/versions/022_edge_write_serialization.py`
- Modify: `backend/app/models/parent_child.py` (comment block ~lines 22-27 only)
- Modify: `backend/app/models/marriage.py` (add/adjust the index-describing comment near `status`/`spouse_order` only)

**Interfaces:**
- Consumes: Task 1's test file — its 8 tests are the acceptance criteria.
- Produces: trigger function with per-clan advisory lock; widened partial unique indexes; six CHECK constraints. Everything else in the schema untouched.

- [ ] **Step 1: Write the migration**

Create `backend/migrations/versions/022_edge_write_serialization.py`:

```python
"""Per-clan edge-write serialization + invariant-matching unique backstops (ADR-025).

H2 (review 2026-07-18): 021's trigger serializes concurrent parent_child writers by
FOR UPDATE-locking the two ENDPOINT persons — writers whose endpoints are disjoint
never serialize, so with committed D→A and B→C, concurrent inserts A→B and C→D both
pass their (pre-race snapshot) cycle walks and COMMIT AN ANCESTRY CYCLE. Fix: a
per-clan pg_advisory_xact_lock at the top of the trigger — the bio-cap count and the
cycle walk are both clan-scoped, so a per-clan critical section makes every writer's
re-check see every earlier writer's committed edges. Two-arg keyspace (classid
728116) cannot collide with the background jobs' one-arg locks 728_115_00x (those
occupy classid 0); hashtext collisions across clans merely over-serialize.

M2a: idx_marriages_unique_pair was partial on status='married', but the app's
"active" (has_active_marriage, and 015's spouse_order index) is status<>'divorced' —
concurrent same-pair widowed/separated creates both landed. Widened; this also
closes tracked race M4 (divorced→active UPDATE now re-checks the index).

M2b: idx_parent_child_unique_edge keyed on relationship_type, but the app forbids
ANY second live link per (parent, child). relationship_type dropped from the key.

Also: CHECK constraints for the five *_precision columns (enum enforced only in
Pydantic until now) and branches self-parenting.

Pre-checks fail the migration loudly (listing rows) if existing data already
violates any widened/new constraint — no silent repair (015/021 precedent).

Revision ID: 022_edge_write_serialization
Revises: 021_parent_child_guard
"""

from __future__ import annotations

from alembic import op

revision: str = "022_edge_write_serialization"
down_revision: str | None = "021_parent_child_guard"
branch_labels = None
depends_on = None

_PRECISION_ENUM = "('exact','year','month','circa','unknown')"

_PRECHECK_MARRIAGE_PAIRS = """
DO $$
DECLARE bad TEXT;
BEGIN
    SELECT string_agg(v.pair, '; ') INTO bad FROM (
        SELECT format('clan=%s pair=%s/%s x%s', created_by_clan_id,
                      LEAST(person1_id, person2_id), GREATEST(person1_id, person2_id),
                      COUNT(*)) AS pair
        FROM marriages
        WHERE status <> 'divorced' AND is_deleted = false
        GROUP BY created_by_clan_id, LEAST(person1_id, person2_id),
                 GREATEST(person1_id, person2_id)
        HAVING COUNT(*) > 1
    ) v;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'cannot widen idx_marriages_unique_pair: pairs with multiple live non-divorced marriages: %', bad;
    END IF;
END $$;
"""

_PRECHECK_EDGE_PAIRS = """
DO $$
DECLARE bad TEXT;
BEGIN
    SELECT string_agg(v.pair, '; ') INTO bad FROM (
        SELECT format('clan=%s edge=%s->%s x%s', created_by_clan_id, parent_id,
                      child_id, COUNT(*)) AS pair
        FROM parent_child
        WHERE is_deleted = false
        GROUP BY created_by_clan_id, parent_id, child_id
        HAVING COUNT(*) > 1
    ) v;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'cannot widen idx_parent_child_unique_edge: pairs with multiple live edges: %', bad;
    END IF;
END $$;
"""

_PRECHECK_PRECISION = """
DO $$
DECLARE bad TEXT;
BEGIN
    SELECT string_agg(v.rec, '; ') INTO bad FROM (
        SELECT format('persons.birth %s', id) AS rec FROM persons
          WHERE birth_date_precision NOT IN {enum}
        UNION ALL
        SELECT format('persons.death %s', id) FROM persons
          WHERE death_date_precision NOT IN {enum}
        UNION ALL
        SELECT format('events.event %s', id) FROM events
          WHERE event_date_precision NOT IN {enum}
        UNION ALL
        SELECT format('marriages.marriage %s', id) FROM marriages
          WHERE marriage_date_precision NOT IN {enum}
        UNION ALL
        SELECT format('marriages.divorce %s', id) FROM marriages
          WHERE divorce_date_precision NOT IN {enum}
    ) v;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'cannot add precision CHECKs: rows with out-of-enum precision: %', bad;
    END IF;
END $$;
""".format(enum=_PRECISION_ENUM)

_PRECHECK_BRANCH_SELF = """
DO $$
DECLARE bad TEXT;
BEGIN
    SELECT string_agg(id::text, ', ') INTO bad FROM branches WHERE parent_branch_id = id;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'cannot add branch self-parent CHECK: self-parenting branches: %', bad;
    END IF;
END $$;
"""

# The 022 function: identical to 021 except for the advisory-lock block.
_FUNCTION_022 = """
CREATE OR REPLACE FUNCTION public.parent_child_integrity_guard() RETURNS trigger AS $$
DECLARE
    bio_count INT;
    cycle_found BOOLEAN;
BEGIN
    -- Soft-deleting an edge can never violate either invariant.
    IF NEW.is_deleted THEN
        RETURN NULL;
    END IF;

    IF NEW.parent_id = NEW.child_id THEN
        RAISE EXCEPTION 'relationship_cycle: person % cannot be their own parent', NEW.child_id
            USING ERRCODE = 'check_violation';
    END IF;

    -- Serialize ALL live-edge writes within a clan (ADR-025). The bio-cap count
    -- and the cycle walk below are both clan-scoped, so a per-clan critical
    -- section makes every writer's re-check see every earlier writer's committed
    -- edges — including writers whose edge ENDPOINTS are disjoint, the race the
    -- per-person FOR UPDATE locks cannot close (H2, review 2026-07-18).
    -- xact-scoped: auto-released at commit/rollback. Two-arg keyspace (classid
    -- 728116) cannot collide with the jobs' one-arg locks 728_115_00x (classid 0);
    -- cross-clan hashtext collisions merely over-serialize (harmless at gia-phả
    -- write rates).
    PERFORM pg_advisory_xact_lock(728116, hashtext(NEW.created_by_clan_id::text));

    -- Person-row locks kept: they additionally serialize against the
    -- claim-approval path (which FOR UPDATEs person rows). Same-clan writers are
    -- already serialized by the advisory lock before reaching these; cross-clan
    -- writers take them in deterministic LEAST/GREATEST order — no deadlock.
    PERFORM 1 FROM public.persons WHERE id = LEAST(NEW.parent_id, NEW.child_id) FOR UPDATE;
    PERFORM 1 FROM public.persons WHERE id = GREATEST(NEW.parent_id, NEW.child_id) FOR UPDATE;

    IF NEW.relationship_type = 'biological' THEN
        SELECT COUNT(*) INTO bio_count
        FROM public.parent_child
        WHERE child_id = NEW.child_id
          AND relationship_type = 'biological'
          AND is_deleted = false
          AND created_by_clan_id = NEW.created_by_clan_id;
        -- The count includes NEW's own row (AFTER trigger).
        IF bio_count > 2 THEN
            RAISE EXCEPTION 'too_many_biological_parents: child % already has 2 live biological parents', NEW.child_id
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    -- parent→child closes a cycle iff child is already an ancestor of parent
    -- (via this clan's live edges). UNION dedupes visited nodes → terminates.
    WITH RECURSIVE anc(id) AS (
        SELECT pc.parent_id FROM public.parent_child pc
        WHERE pc.child_id = NEW.parent_id AND pc.is_deleted = false
          AND pc.created_by_clan_id = NEW.created_by_clan_id
        UNION
        SELECT pc.parent_id FROM public.parent_child pc
        JOIN anc ON pc.child_id = anc.id
        WHERE pc.is_deleted = false AND pc.created_by_clan_id = NEW.created_by_clan_id
    )
    SELECT EXISTS (SELECT 1 FROM anc WHERE anc.id = NEW.child_id) INTO cycle_found;
    IF cycle_found THEN
        RAISE EXCEPTION 'relationship_cycle: edge % -> % closes an ancestry cycle', NEW.parent_id, NEW.child_id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

# 021's function body, verbatim, for downgrade (no advisory lock).
_FUNCTION_021 = """
CREATE OR REPLACE FUNCTION public.parent_child_integrity_guard() RETURNS trigger AS $$
DECLARE
    bio_count INT;
    cycle_found BOOLEAN;
BEGIN
    IF NEW.is_deleted THEN
        RETURN NULL;
    END IF;

    IF NEW.parent_id = NEW.child_id THEN
        RAISE EXCEPTION 'relationship_cycle: person % cannot be their own parent', NEW.child_id
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM 1 FROM public.persons WHERE id = LEAST(NEW.parent_id, NEW.child_id) FOR UPDATE;
    PERFORM 1 FROM public.persons WHERE id = GREATEST(NEW.parent_id, NEW.child_id) FOR UPDATE;

    IF NEW.relationship_type = 'biological' THEN
        SELECT COUNT(*) INTO bio_count
        FROM public.parent_child
        WHERE child_id = NEW.child_id
          AND relationship_type = 'biological'
          AND is_deleted = false
          AND created_by_clan_id = NEW.created_by_clan_id;
        IF bio_count > 2 THEN
            RAISE EXCEPTION 'too_many_biological_parents: child % already has 2 live biological parents', NEW.child_id
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    WITH RECURSIVE anc(id) AS (
        SELECT pc.parent_id FROM public.parent_child pc
        WHERE pc.child_id = NEW.parent_id AND pc.is_deleted = false
          AND pc.created_by_clan_id = NEW.created_by_clan_id
        UNION
        SELECT pc.parent_id FROM public.parent_child pc
        JOIN anc ON pc.child_id = anc.id
        WHERE pc.is_deleted = false AND pc.created_by_clan_id = NEW.created_by_clan_id
    )
    SELECT EXISTS (SELECT 1 FROM anc WHERE anc.id = NEW.child_id) INTO cycle_found;
    IF cycle_found THEN
        RAISE EXCEPTION 'relationship_cycle: edge % -> % closes an ancestry cycle', NEW.parent_id, NEW.child_id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

_CHECKS = [
    ("persons", "ck_persons_birth_precision", f"birth_date_precision IN {_PRECISION_ENUM}"),
    ("persons", "ck_persons_death_precision", f"death_date_precision IN {_PRECISION_ENUM}"),
    ("events", "ck_events_event_precision", f"event_date_precision IN {_PRECISION_ENUM}"),
    (
        "marriages",
        "ck_marriages_marriage_precision",
        f"marriage_date_precision IN {_PRECISION_ENUM}",
    ),
    (
        "marriages",
        "ck_marriages_divorce_precision",
        f"divorce_date_precision IN {_PRECISION_ENUM}",
    ),
    (
        "branches",
        "ck_branches_no_self_parent",
        "parent_branch_id IS NULL OR parent_branch_id <> id",
    ),
]


def upgrade() -> None:
    op.execute(_PRECHECK_MARRIAGE_PAIRS)
    op.execute(_PRECHECK_EDGE_PAIRS)
    op.execute(_PRECHECK_PRECISION)
    op.execute(_PRECHECK_BRANCH_SELF)

    op.execute(_FUNCTION_022)

    op.execute("DROP INDEX IF EXISTS idx_marriages_unique_pair")
    op.execute(
        "CREATE UNIQUE INDEX idx_marriages_unique_pair ON marriages "
        "(created_by_clan_id, LEAST(person1_id, person2_id), "
        "GREATEST(person1_id, person2_id)) "
        "WHERE status <> 'divorced' AND is_deleted = false"
    )
    op.execute("DROP INDEX IF EXISTS idx_parent_child_unique_edge")
    op.execute(
        "CREATE UNIQUE INDEX idx_parent_child_unique_edge ON parent_child "
        "(created_by_clan_id, parent_id, child_id) "
        "WHERE is_deleted = false"
    )

    for table, name, expr in _CHECKS:
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expr})")


def downgrade() -> None:
    for table, name, _ in reversed(_CHECKS):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")

    op.execute("DROP INDEX IF EXISTS idx_parent_child_unique_edge")
    op.execute(
        "CREATE UNIQUE INDEX idx_parent_child_unique_edge ON parent_child "
        "(created_by_clan_id, parent_id, child_id, relationship_type) "
        "WHERE is_deleted = false"
    )
    op.execute("DROP INDEX IF EXISTS idx_marriages_unique_pair")
    op.execute(
        "CREATE UNIQUE INDEX idx_marriages_unique_pair ON marriages "
        "(created_by_clan_id, LEAST(person1_id, person2_id), "
        "GREATEST(person1_id, person2_id), status) "
        "WHERE status = 'married' AND is_deleted = false"
    )

    op.execute(_FUNCTION_021)
```

Before finalizing, verify `_FUNCTION_021` is byte-identical to the function body in `migrations/versions/021_parent_child_guard.py` (minus its explanatory comments, which were kept there — copy 021's version verbatim including comments if you prefer; behavior is what matters).

- [ ] **Step 2: Run the Task 1 tests — all 8 must pass**

Run: `cd backend && uv run pytest tests/integration/test_edge_write_serialization.py -v`
Expected: 8/8 PASS. (The integration conftest rebuilds the test DB from the full chain each session, so the new migration applies automatically.)

- [ ] **Step 3: Run the migration/backstop/relationship suites**

Run: `cd backend && uv run pytest tests/integration/test_parent_child_db_backstop.py tests/integration/test_schema_baseline.py tests/integration -q -k "migration or backstop or relationship or marriage"`
Then the full suite: `uv run pytest -q`
Expected: PASS. If any existing test deliberately created two live same-pair marriages (now forbidden), inspect it: if the test itself pinned the OLD (narrower) index semantics, update it to the new invariant and say so in your report; do not weaken the migration.

- [ ] **Step 4: Update the model comments (comment-only)**

In `backend/app/models/parent_child.py`, update the comment block above `__table_args__` to say the unique index is per (clan, parent, child) regardless of relationship_type (migrations 006/007/022) and that the ADR-023/ADR-025 trigger serializes per clan.
In `backend/app/models/marriage.py`, add one comment near `status` noting the DB-enforced invariant: at most one live non-divorced marriage per (clan, pair) — `idx_marriages_unique_pair` (022), matching `has_active_marriage`.

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/versions/022_edge_write_serialization.py backend/app/models/parent_child.py backend/app/models/marriage.py
git commit -m "fix(db): per-clan edge-write serialization + invariant-matching uniques + CHECKs (ADR-025)"
```

---

### Task 3: ADR-025 + docs sync

**Files:**
- Create: `docs/decisions/025-per-clan-edge-write-serialization.md`
- Modify: `docs/decisions/README.md` (add the ADR-025 row, matching the table's format)
- Possibly modify: `docs/architecture/data-model.md` and any other doc surfaced by the grep in Step 1.

- [ ] **Step 1: Grep for every doc describing the changed constraints**

Run: `grep -rn "unique_pair\|unique_edge\|advisory\|ADR-023\|acyclicity\|status = 'married'\|relationship_type" docs/architecture docs/decisions docs/contracts --include='*.md' | grep -v "superpowers\|review-2026-07-18"`
Every hit describing the OLD index semantics ("unique per status", "keyed on relationship_type", "unique among married") or claiming the trigger fully serializes concurrent writers must be updated. Dispose of every hit explicitly in your report (updated / not-applicable-because).

- [ ] **Step 2: Write ADR-025**

`docs/decisions/025-per-clan-edge-write-serialization.md`, following the house ADR format (look at `docs/decisions/023-*.md` for structure). Content: Context (H2 disjoint-endpoint race with the concrete D→A/B→C counterexample; M2a/M2b invariant-narrower indexes; M4); Decision (per-clan `pg_advisory_xact_lock(728116, hashtext(clan_id))` in the trigger — clan-scoped invariants make a per-clan critical section sufficient; widened partial uniques matching `has_active_marriage` / any-live-edge-per-pair; six CHECKs); Consequences (per-clan edge-write serialization ceiling — negligible at human genealogy-editing rates; keyspace isolation from job locks 728_115_00x; M4 closed as a side effect; migration 022 prechecks fail loudly on violating data); Alternatives rejected (SERIALIZABLE + retry plumbing through handler/UoW — more moving parts for the same guarantee; global lock — needless cross-clan coupling).

- [ ] **Step 3: Update `docs/decisions/README.md`** — add the 025 row (status Accepted, date 2026-07-18).

- [ ] **Step 4: Re-run the Step 1 grep; confirm no stale semantics remain. Commit.**

```bash
git add docs/
git commit -m "docs(adr): ADR-025 per-clan edge-write serialization + invariant-matching uniques"
```

---

### Task 4: Full gate + branch verification (controller-run)

- [ ] **Step 1:** `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` — all five green.
- [ ] **Step 2:** Confirm Task 1's RED run showed the cycle/duplicate corruption landing before 022 existed (the negative control for the whole migration). No code change.
