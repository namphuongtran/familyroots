# ADR-031: Cross-Clan Edge Prevention Is an Application-Layer Guarantee (No DB Trigger)

## Status
Accepted (2026-07-25).

## Context

The 2026-07-18 backend review (`docs/architecture/backend-review-2026-07-18.md`,
finding **M10**) noted that the graph/attachment tables — `parent_child`, `marriages`,
`events`, `documents` — have foreign keys to `persons.id` and a `created_by_clan_id`,
but **no database-level constraint requires the referenced person to belong to that
clan**. Persons are not clan-scoped rows: `persons` is a global entity, its
`created_by_clan_id` is a *nullable origin* (`ON DELETE SET NULL`), and clan membership
is the many-to-many `clan_memberships` (a person can belong to several clans). So a
person's "clan" is defined by membership, not by a column on the edge.

A cross-clan edge — an edge in clan C whose endpoint person is **not** a member of C —
would be traversed by the clan-C tree CTEs (which filter edges by
`created_by_clan_id = C`), pulling a non-member person into C's tree.

Today this is prevented at the **application/repository layer**, consistently:

- Every relationship write calls `ensure_persons_in_clan([...], clan_id)`
  (`app/application/relationship/handlers.py`), which resolves membership via
  `persons_in_clan` → a `clan_memberships` join
  (`app/infrastructure/persistence/relationship_repository.py`), and raises
  `404 person_not_found` if any endpoint is not a live member of the clan.
- The read side is symmetric: person / tree queries `JOIN clan_memberships`, so a
  non-member person does not surface in a clan's data.
- This is proven **two-sided** by `test_cross_clan_edge_guard.py` (a write in clan B
  referencing a clan-A-only person is rejected; a same-clan write succeeds) alongside
  the existing read-side `test_relationship_isolation.py`.

The review offered two options: a `clan_memberships`-existence **trigger** backstop, or
**explicitly accept** the application-layer guarantee.

## Decision

**Accept the application-layer guarantee; do not add a membership trigger.**

1. Cross-clan-edge prevention remains enforced by the application/repository layer
   (`ensure_persons_in_clan` on every write; membership joins on every read),
   regression-pinned two-sided by `test_cross_clan_edge_guard.py`.
2. The intended **database-level** defense-in-depth is **Supabase RLS (layer-2,
   ADR-008 / SP-3)** — currently a `documents`-only pilot, inert for app traffic because
   the app connects as a privileged role. RLS, once activated, enforces clan isolation
   at the engine level across all clan-scoped tables — a more comprehensive backstop
   than per-table membership triggers, without duplicating that logic in PL/pgSQL.
3. A dedicated `clan_memberships`-existence trigger is **not** added, because it would
   (a) duplicate what RLS is purpose-built to do, (b) impose a per-write membership
   `EXISTS` and a within-transaction flush-ordering constraint (membership before edge),
   and (c) require reworking ~17 integration fixtures that seed edges via raw SQL without
   membership rows — cost disproportionate to a defense the app already enforces and RLS
   will subsume.

## Consequences

- **Residual risk (accepted):** a raw-SQL job or a future write path that bypasses
  `ensure_persons_in_clan` could insert a cross-clan edge; the DB would not stop it until
  RLS layer-2 is active. This is a known, bounded gap — all current write paths go
  through the guarded handlers, and the two-sided pin test would catch a regression that
  drops the guard.
- No schema change, no migration, no per-write DB cost, no test-fixture churn.
- If RLS layer-2 is ever shelved, revisit this decision — the membership trigger becomes
  the fallback DB backstop (the review's Option A), and this ADR should be superseded.

## Alternatives considered

- **`clan_memberships`-existence trigger** (review Option A) — rejected as above:
  duplicates RLS, real write/test cost, disproportionate to an app-enforced invariant.
- **A same-origin-clan CHECK** (`persons.created_by_clan_id = edge.created_by_clan_id`) —
  rejected: `created_by_clan_id` is a nullable origin, not membership, so it is both
  wrong for legitimately shared/married-in persons and unsatisfiable for `NULL`-origin
  persons.
