# ADR-023: DB Backstop for Genealogy Graph Invariants (parent_child trigger)

## Status
Accepted, shipped (2026-07-17, migration 021)

> **Update (2026-07-18):** Amended by [ADR-025](025-per-clan-edge-write-serialization.md)
> (migration `022_edge_write_serialization`): the "Serialization" bullet below
> describes the 021 trigger, which serialized concurrent writers by locking
> only the two edge **endpoint** persons — writers with disjoint endpoints
> could still race an ancestry cycle into existence (H2, review 2026-07-18).
> 022 added a per-clan `pg_advisory_xact_lock` ahead of those person locks to
> close it. The bio-parent cap and acyclicity walk described below are
> unchanged. `idx_marriages_unique_pair` and `idx_parent_child_unique_edge`,
> referenced elsewhere in this repo in the context of this trigger, were also
> widened by 022 — see ADR-025.

## Context

Two graph invariants protect the gia phả from corruption:

1. A child has at most **2 biological parents**.
2. The parent-child graph is **acyclic**.

Both were enforced only by application-layer SELECT-then-INSERT pre-checks
(`RelationshipValidator`). Under READ COMMITTED, two editors concurrently
adding different "biological fathers" both pass the pre-check and both
commit — the child ends with 3 biological parents. Concurrent A→B and B→A
inserts likewise commit an ancestry cycle (read paths are path-array-guarded
so nothing hangs, but the graph is corrupt until manual repair).
`spouse_order` received exactly this kind of DB backstop in migration 015;
these two invariants did not. A corrupt heritage graph is worse than a
rejected write, so the database itself must own these invariants.

## Decision

Migration `021_parent_child_guard` installs an AFTER INSERT/UPDATE row
trigger on `parent_child` (live rows only):

- **Serialization**: the trigger locks both endpoint `persons` rows
  `FOR UPDATE` in deterministic LEAST/GREATEST order. Concurrent writers
  touching the same persons queue; when a waiter proceeds, its re-checks
  run on a fresh READ COMMITTED snapshot that includes the previous
  writer's committed edges — closing the pre-check race without requiring
  SERIALIZABLE isolation.
- **Bio-parent cap**: for biological edges, re-count live biological
  parents of the child within the owning clan (the count includes the new
  row); more than 2 → `RAISE ... too_many_biological_parents`
  (SQLSTATE 23514).
- **Acyclicity**: the new edge parent→child closes a cycle iff the child is
  already an ancestor of the parent via the clan's live edges — walked with
  a `UNION` recursive CTE (visited-set semantics, terminates even over
  corrupt data); hit → `RAISE ... relationship_cycle`.
- **Migration pre-checks** fail loudly (listing offending rows) if existing
  data already violates either invariant — no silent repair.
- **Error mapping**: `integrity_error_handler` maps these two trigger slugs
  (23514) to the SAME 409 codes the app validator uses
  (`relationship.too_many_biological_parents`, `relationship.creates_cycle`)
  — one wire contract whether the pre-check or the backstop rejected. Any
  other check_violation still surfaces as the loud 500 (likely a bug).

The application validator remains the primary check (fast, precise,
localized 409/422 before any write); the trigger fires only on true races
or out-of-band writes.

## Consequences

- Every parent_child write takes two person-row locks — negligible for
  human-driven edits; bulk imports serialize per family branch, which is
  acceptable.
- Locking person rows FOR UPDATE briefly contends with person PATCHes on
  the same rows (both short transactions).
- The trigger's cycle walk is O(ancestors) per insert with the
  `idx_parent_child_parent_clan_live` index (migration 018) supporting it.
- Self-edges remain rejected by the baseline CHECK
  (`ck_parent_child_parent_child_no_self`); the trigger keeps its own guard
  as defense should that constraint ever be dropped.

## Alternatives considered

- **SERIALIZABLE isolation for relationship writes** — rejected: global
  cost and retry loops for a per-row problem.
- **App-layer advisory locks** — rejected: only guards writers that go
  through the app; the point of a backstop is protecting the data from
  every writer.
- **EXCLUDE constraint / partial unique for the bio cap** — a unique index
  can enforce ≤1, not ≤2, without hacks (slot columns); the cycle invariant
  has no declarative form at all, so a trigger is required regardless.
