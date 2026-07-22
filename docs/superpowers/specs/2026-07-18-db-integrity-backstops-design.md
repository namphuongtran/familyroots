# DB Integrity Backstops (A2) — Design

**Date:** 2026-07-18
**Source findings:** H2, M2 (+ Lows: precision CHECKs, branch self-parent CHECK) in
`docs/architecture/backend-review-2026-07-18.md`; also closes tracked follow-up M4
(concurrent divorced→active same-pair flip) as a side effect.
**Owner decision:** per-clan advisory lock in the trigger (chosen over SERIALIZABLE
edge writes, which would need retry plumbing through handler/UoW).

## Problem

Four places where the database permits states the application forbids:

1. **H2 — cycle race with disjoint endpoints.** The ADR-023 trigger
   (`migrations/versions/021_parent_child_guard.py:89-90`) serializes concurrent
   edge writers by `FOR UPDATE`-locking the two endpoint persons. Writers whose
   endpoints don't overlap never serialize: with committed edges `D→A`, `B→C`,
   txn1 inserts `A→B` (locks A,B — walk sees no cycle), txn2 concurrently inserts
   `C→D` (locks C,D — walk sees no cycle); both commit → ancestry cycle
   `A→B→C→D→A`. Manual repair; re-running 021's precheck then fails.
2. **M2a — marriage-pair unique narrower than the invariant.**
   `idx_marriages_unique_pair` (migration 007) is partial on
   `status = 'married'`, but the app's `has_active_marriage`
   (`relationship_repository.py:262-282`) — and migration 015's own spouse_order
   index — define active as `status <> 'divorced'`. Two concurrent same-pair
   creates where either row is `widowed`/`separated` both pass the pre-check and
   both insert. Related tracked race M4 (divorced→active flip) exploits the same
   narrowness via UPDATE.
3. **M2b — parent-child edge unique keyed on `relationship_type`.**
   `idx_parent_child_unique_edge` (007) allows a concurrent `biological` +
   `step` insert for the same (parent, child); the app forbids any second live
   link per pair (`has_parent_child_link` ignores type).
4. **Missing CHECKs.** The five `*_precision` columns (migration 012:
   `persons.birth_date_precision`, `persons.death_date_precision`,
   `events.event_date_precision`, `marriages.marriage_date_precision`,
   `marriages.divorce_date_precision`) are free-text `VARCHAR(10)` — the enum is
   enforced only in Pydantic. `branches.parent_branch_id` permits self-parenting
   at the DB (app guards only on update).

## Design — one migration (`022_edge_write_serialization`), ADR-025

### 1. Per-clan advisory lock in the trigger (H2)

`CREATE OR REPLACE FUNCTION public.parent_child_integrity_guard()` — same function,
one addition after the self-parent check, before the person `FOR UPDATE` locks:

```sql
    -- Serialize ALL live-edge writes within a clan (ADR-025). The bio-cap count
    -- and the cycle walk are both clan-scoped, so a per-clan critical section
    -- makes every writer's re-check see every earlier writer's committed edges —
    -- including writers whose edge endpoints are disjoint (the race the per-person
    -- FOR UPDATE locks below cannot close). xact-scoped: auto-released at
    -- commit/rollback. Two-arg keyspace (classid 728116) cannot collide with the
    -- jobs' one-arg locks 728_115_00x (classid 0); hashtext collisions across
    -- clans merely over-serialize, which is harmless at genealogy write rates.
    PERFORM pg_advisory_xact_lock(728116, hashtext(NEW.created_by_clan_id::text));
```

The person `FOR UPDATE` locks stay (they additionally serialize against the
claim-approval path, which locks person rows; deterministic order still prevents
deadlock — same-clan writers are already serialized by the advisory lock before
reaching them, and cross-clan writers take them in LEAST/GREATEST order).

Docstring/comment updates in the function tell the truth about what serializes what.

### 2. Widen the unique backstops to the app invariants (M2a, M2b)

Same index names (the 23505 handler maps ANY unique violation to the stable 409
`conflict` envelope, so names don't affect the API contract — but keeping them
avoids churn in comments/docs):

```sql
DROP INDEX idx_marriages_unique_pair;
CREATE UNIQUE INDEX idx_marriages_unique_pair ON marriages
  (created_by_clan_id, LEAST(person1_id, person2_id), GREATEST(person1_id, person2_id))
  WHERE status <> 'divorced' AND is_deleted = false;

DROP INDEX idx_parent_child_unique_edge;
CREATE UNIQUE INDEX idx_parent_child_unique_edge ON parent_child
  (created_by_clan_id, parent_id, child_id)
  WHERE is_deleted = false;
```

- Marriage: `status` leaves both the key and the predicate-narrowing — one live
  non-divorced marriage per pair per clan. Divorce→remarry same pair still works
  (divorced rows leave the partial index). UPDATEs re-check the index, so the
  tracked M4 flip race is closed too.
- Parent-child: one live edge per (clan, parent, child) regardless of type.

### 3. CHECK constraints (Lows)

```sql
ALTER TABLE persons   ADD CONSTRAINT ck_persons_birth_precision   CHECK (birth_date_precision   IN ('exact','year','month','circa','unknown'));
ALTER TABLE persons   ADD CONSTRAINT ck_persons_death_precision   CHECK (death_date_precision   IN ('exact','year','month','circa','unknown'));
ALTER TABLE events    ADD CONSTRAINT ck_events_event_precision    CHECK (event_date_precision    IN ('exact','year','month','circa','unknown'));
ALTER TABLE marriages ADD CONSTRAINT ck_marriages_marriage_precision CHECK (marriage_date_precision IN ('exact','year','month','circa','unknown'));
ALTER TABLE marriages ADD CONSTRAINT ck_marriages_divorce_precision  CHECK (divorce_date_precision  IN ('exact','year','month','circa','unknown'));
ALTER TABLE branches  ADD CONSTRAINT ck_branches_no_self_parent   CHECK (parent_branch_id IS NULL OR parent_branch_id <> id);
```

(Exact nullability handled per column — the precision columns are NOT NULL with
default 'exact', so a plain IN check suffices; verify in implementation.)

### 4. Prechecks — fail loudly, never repair (house style, as 015/021)

Before each change, list offending rows and RAISE:
- pairs with >1 live non-divorced marriage (per clan);
- (clan, parent, child) pairs with >1 live edge;
- rows with precision values outside the enum;
- self-parenting branches.

### 5. Downgrade

Restores the 021 function body (no advisory lock), the 007 index definitions, and
drops the six CHECK constraints.

### 6. ADR-025

`docs/decisions/025-per-clan-edge-write-serialization.md`: context (H2 race,
invariant-narrower indexes), decision (per-clan `pg_advisory_xact_lock` in the
trigger + invariant-matching partial uniques), consequences (per-clan edge-write
throughput ceiling — acceptable; keyspace note vs job locks; M4 closed), the
rejected alternative (SERIALIZABLE + retry). Index docs in
`docs/architecture/data-model.md` updated to the new definitions.

## What does NOT change

- No application code changes. The app-layer validator pre-checks stay (they give
  friendly, specific 409 codes before the DB is ever hit; the DB is the backstop).
- Error contract unchanged: trigger raises map to the same 23514 slugs
  (`relationship_cycle`, `too_many_biological_parents`); widened uniques surface
  as the existing 409 `conflict` via the 23505 handler.
- `models/parent_child.py` / `models/marriage.py` comments describing the indexes
  are updated to match (comment-only).
- The per-clan scoping asymmetry of the cycle walk vs 021's global precheck
  (review Low #10) is explicitly OUT of scope — separate decision.
- `clans.founded_year` CHECK relaxation (review Low #13) — lows batch, not here.

## Tests (all real-PG integration; RED-first where behavior changes)

1. **H2 race test** (new, in `test_parent_child_db_backstop.py` style): seed
   `D→A`, `B→C`; two concurrent transactions insert `A→B` and `C→D`. RED today:
   both commit and a cycle exists (assert via the recursive CTE). GREEN after 022:
   exactly one commits, the loser gets the `relationship_cycle` check_violation;
   assert no cycle exists. Include a negative control (same harness, edges that do
   NOT close a cycle → both succeed sequentially… the second blocks on the clan
   lock until the first commits, then succeeds).
2. **M2a race test**: two concurrent same-pair creates with `status='widowed'`.
   RED today: both insert. GREEN: loser gets 23505. Plus non-race guards: divorced
   + new married same pair still allowed; two live `separated`+`married` same pair
   rejected.
3. **M2b race test**: concurrent `biological` + `step` for same (parent, child).
   RED today: both insert. GREEN: loser 23505.
4. **CHECK sabotage tests**: raw INSERT/UPDATE with `precision='approx'` fails
   with 23514; branch `parent_branch_id = id` fails.
5. **Precheck tests**: on a DB seeded with a violating row (via raw SQL bypassing
   the app), running the 022 upgrade fails loudly listing the row (pattern:
   existing migration prechecks are covered by `test_schema_baseline.py`-adjacent
   migration tests — implementer follows the 015/021 precheck-test pattern if one
   exists, else adds a focused one).
6. **Migration round-trip**: existing `base→head` test must stay green (022
   reversible).
7. **HTTP-level regression**: existing relationship API tests stay green — the
   validator still produces its specific codes; the trigger/index only fires on
   races the validator can't see.

## Performance note

The advisory lock adds one in-memory lock acquisition per edge write and
serializes writes per clan — at real gia-phả editing rates (humans entering
ancestors) contention is negligible. Reads are unaffected. The widened marriage
index is smaller than before (fewer key columns). No new index maintenance cost.
