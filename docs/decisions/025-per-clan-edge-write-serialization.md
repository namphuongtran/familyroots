# ADR-025: Per-Clan Edge-Write Serialization + Invariant-Matching Unique Backstops

## Status
Accepted, shipped (2026-07-18, migration 022). Amends [ADR-023](023-parent-child-db-backstop.md).

## Context

The 2026-07-18 backend review (`docs/architecture/backend-review-2026-07-18.md`)
found the ADR-023 backstops narrower than the invariants they were meant to
protect, in three ways:

- **H2 — disjoint-endpoint cycle race.** The 021 trigger serializes concurrent
  `parent_child` writers by `FOR UPDATE`-locking only the two edge **endpoint**
  persons (deterministic LEAST/GREATEST order). Writers whose endpoints don't
  overlap never contend, so the acyclicity re-check can still race: with
  committed edges `D→A` and `B→C` already in place, a concurrent insert of
  `A→B` (locking A, B) and `C→D` (locking C, D) have **disjoint lock sets** —
  neither sees the other's in-flight row, both re-checks pass on their
  pre-race snapshot, and both COMMIT. The result is an ancestry cycle
  `A→B→C→D→A` sitting live in the graph, requiring manual repair (and 021's
  own precheck would fail loudly if the migration were re-run against it).
  The bio-parent cap re-check is unaffected — it's anchored on the (locked)
  child, so it always sees a consistent count.
- **M2a — `idx_marriages_unique_pair` narrower than `has_active_marriage`.**
  The index (migration 007) was partial on `status='married'`, but the app
  treats a marriage as active whenever `status <> 'divorced'`
  (`has_active_marriage`, and 015's `spouse_order` index uses the same
  definition). Two concurrent same-pair creates that both land in `widowed`
  or `separated` skip the unique index entirely and both insert — same
  invariant gap as the acyclicity race, just declarative instead of
  procedural.
- **M2b — `idx_parent_child_unique_edge` keyed on `relationship_type`.** The
  app forbids any second live link between the same parent and child
  regardless of type (`relationship.duplicate_parent_child`), but the index
  (migration 007) includes `relationship_type` in its key, so a concurrent
  `biological` + `adopted` insert for the same pair both land.
- **Tracked race M4 (divorced→active flip).** A `PATCH` that flips a
  marriage's `status` away from `divorced` re-validates in the app layer, but
  under the old `status='married'`-only index a concurrent flip-to-`widowed`
  bypassed the index the same way a concurrent create did. Widening the index
  to `status <> 'divorced'` closes this as a side effect, because an `UPDATE`
  re-checks the (now-matching) partial index just like an `INSERT` does.
- Five `*_precision` columns (persons birth/death, events, marriages
  marriage/divorce) and `branches.parent_branch_id` self-parenting had no
  database-level CHECK — the precision enum was only enforced in Pydantic,
  and self-parenting branches had no backstop at all.

## Decision

Migration `022_edge_write_serialization` (revises `021_parent_child_guard`):

- **Per-clan advisory transaction lock, in a dedicated BEFORE ROW trigger.**
  A new `trg_parent_child_clan_lock` (`parent_child_clan_lock()`, BEFORE
  INSERT/UPDATE of the same columns the guard watches) takes
  `pg_advisory_xact_lock(728116, hashtext(NEW.created_by_clan_id::text))` for
  every live-edge write. Both invariants the AFTER guard protects (bio-parent
  cap, acyclicity) are scoped to a single clan's live edges, so a per-clan
  critical section is sufficient: it makes every writer's re-check —
  regardless of which persons its edge touches — see every earlier same-clan
  writer's committed edges. This closes H2 without a table-wide lock.
  **The BEFORE placement is load-bearing.** The write's foreign-key checks
  take `FOR KEY SHARE` on both endpoint persons before any AFTER trigger
  runs; a first draft that took the advisory lock inside the AFTER guard
  therefore deadlocked ~79% of rounds on the most common concurrent edit
  (two editors adding father→child and mother→child at once): writer 1 held
  the clan lock wanting the child's row, writer 2 held the child's row (FK)
  wanting the clan lock. Taken in the BEFORE phase, a same-clan writer blocks
  before acquiring any person row lock — same-clan writers cannot deadlock.
  The lock is xact-scoped (auto-released at commit/rollback). Its
  two-argument keyspace (classid `728116`) is disjoint from the scheduler
  jobs' single-argument locks `728_115_001`/`728_115_002` (classid `0`) — no
  collision is possible. `hashtext` collisions across different clans' ids
  merely over-serialize (harmless at gia-phả editing rates). The person
  `FOR UPDATE` locks in the AFTER guard are kept (they additionally serialize
  against the claim-approval path, which locks person rows independently).
  **Known residual (pre-existing since 021, NOT introduced here):** two
  writers from *different clans* editing edges over the same shared persons
  take different clan locks, then can hit the classic `KEY SHARE` →
  `FOR UPDATE` upgrade deadlock on the person rows. This is rare (requires
  cross-clan concurrent edits of shared people), rolls back cleanly (no
  corruption), and today surfaces as a 500 — follow-up ticket: map SQLSTATE
  `40P01` to the 409 conflict envelope so the losing editor gets a clean
  retryable error.
- **`idx_marriages_unique_pair` widened** to
  `(created_by_clan_id, LEAST(person1_id, person2_id), GREATEST(person1_id, person2_id))`
  partial `WHERE status <> 'divorced' AND is_deleted = false` — at most one
  live, non-divorced marriage per pair per clan, now matching
  `has_active_marriage` exactly (and closing M4 as described above).
- **`idx_parent_child_unique_edge` narrowed to key on the pair only**:
  `(created_by_clan_id, parent_id, child_id) WHERE is_deleted = false` —
  `relationship_type` dropped from the key, so at most one live edge exists
  per (parent, child) per clan regardless of type.
- **Six new CHECK constraints**: `ck_persons_birth_precision`,
  `ck_persons_death_precision`, `ck_events_event_precision`,
  `ck_marriages_marriage_precision`, `ck_marriages_divorce_precision` (all
  `IN ('exact','year','month','circa','unknown')`), and
  `ck_branches_no_self_parent` (`parent_branch_id IS NULL OR parent_branch_id <> id`).
- **Prechecks fail the migration loudly** (listing every violating row) if
  existing data already violates a widened or new constraint — no silent
  repair, consistent with 015/021 precedent.
- Downgrade restores the 021 function body verbatim, the two original index
  definitions (`status='married'` / `relationship_type` in the key), and
  drops the six CHECKs.

Error mapping is unchanged from ADR-023: the two `RAISE ... USING ERRCODE =
'check_violation'` slugs still map to `relationship.too_many_biological_parents`
/ `relationship.creates_cycle` (409); the widened unique indexes still surface
through the generic `23505` → 409 `conflict` handler. No application code
changes.

## Consequences

- **Per-clan edge-write serialization ceiling.** Every `parent_child` write
  now takes a clan-wide advisory lock for the duration of its transaction, in
  addition to the two person-row locks. Writers touching the same clan
  (regardless of which persons) now queue behind each other — a strictly
  wider critical section than 021's per-person one. This is negligible at
  human genealogy-editing rates and bulk imports already serialized per
  family branch under 021; it does not change behavior for writers touching
  different clans.
- **Keyspace isolation preserved.** The advisory lock's two-argument form
  cannot collide with the scheduler jobs' single-argument locks
  (`728_115_001`/`728_115_002`), so this change has no interaction with
  `docs/architecture/notifications-scheduler.md`'s multi-replica election.
- **M4 closed as a side effect** of widening `idx_marriages_unique_pair` —
  no separate fix was needed for the divorced→active flip race.
- **Migration 022 prechecks fail loudly** on any pre-existing data that
  already violates a widened or new constraint, per house precedent — the
  operator gets a listed set of offending rows, not a silent migration or a
  silent repair.
- **Cross-clan residual deadlock (pre-existing, unchanged).** Concurrent
  edge writes from different clans over the same shared persons can still hit
  the 021-era `KEY SHARE` → `FOR UPDATE` upgrade deadlock (see Decision);
  rare, rolls back cleanly, surfaces as a 500 today. Follow-up ticket: map
  SQLSTATE `40P01` to the 409 conflict envelope.
- Downgrading is exact: 022's `downgrade()` drops the BEFORE-row clan-lock
  trigger/function and restores the 021 trigger body and both original
  (narrower) index definitions byte-for-byte.

## Alternatives considered

- **SERIALIZABLE isolation for relationship writes, with retry plumbing in
  the handler/UoW** — rejected: closes the same race but needs
  serialization-failure detection and retry logic threaded through the
  command handler and `SqlAlchemyUnitOfWork`, more moving parts than a single
  `pg_advisory_xact_lock` call for a race that's clan-scoped, not
  table-scoped.
- **A single global advisory lock (no clan key)** — rejected: both invariants
  are clan-scoped (a cycle or a bio-parent overcount can only ever form
  within one clan's live edges, since every read/count/walk in the trigger
  already filters on `created_by_clan_id`), so serializing across all clans
  would be needless cross-clan coupling — one clan's editing session would
  block every other clan's writes for no correctness benefit.
