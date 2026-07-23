# ADR-026: Admin-Designated Single Founder (Thủy Tổ) + Deterministic Read

## Status
Accepted, shipped (2026-07-18, migration 023).

## Context

The 2026-07-18 backend review (`docs/architecture/backend-review-2026-07-18.md`)
found the `is_founder` flag on `clan_memberships` structurally unreachable and
its read path nondeterministic:

- **H3 — `is_founder` unreachable, `find_clan_founder` nondeterministic.**
  `clan_memberships.is_founder` existed in the schema and was read by
  `find_clan_founder` (`app/services/tree_builder.py`) to root `GET /tree` and
  anchor đời (thủy tổ = 1), but **no write path ever set it** —
  `PersonCreateRequest` has no `is_founder`/founder field, and no admin
  endpoint existed to flip it. Every clan with any genealogy data therefore
  had **zero** live founders, and `find_clan_founder`'s query was a bare
  `... WHERE is_founder = true LIMIT 1` with no `ORDER BY` — even if a row
  were ever set (by a future internal caller, a data migration, or manual SQL),
  Postgres does not guarantee which matching row a plan-dependent `LIMIT 1`
  returns, so a clan that somehow ended up with 2+ live founder rows (a
  plausible outcome of any hand-rolled fix, since nothing in the schema
  prevented it) would nondeterministically re-root its whole tree — and every
  đời value with it — between calls or after a query-plan change.
- **Consequence:** `GET /tree` without an explicit `root_person_id` 404s
  `clan_founder_not_found` for every clan today, and đời (generation) is
  `null` everywhere a tree only reaches nodes through the missing founder —
  the graph-computed đời feature (ADR-012) was effectively dead on arrival
  for any clan onboarded after that ADR shipped.

## Decision

- **`PUT /clans/me/founder`** (Task 1): admin-only endpoint, body
  `{person_id}`, that designates or corrects the clan's thủy tổ. Idempotent
  (re-designating the current founder is a no-op write) and a **swap**
  otherwise — see `rest-clans-api.md` for the full contract.
- **Migration 023 — `uq_clan_memberships_one_founder`**: a partial unique
  index on `clan_memberships (clan_id) WHERE is_founder = true`. Exactly one
  live founder per clan is now a DB-enforced invariant, not an application
  convention — a concurrent write that would create a second live founder row
  for a clan hits `23505` (unique_violation) at commit, surfaced by the
  generic integrity-error handler as the standard `conflict` 409 (see
  `error-codes.md`), never silently creating a second root.
- **Deterministic `find_clan_founder`** (Task 2): the query is now
  `ORDER BY joined_at ASC NULLS LAST, person_id LIMIT 1` — a stable tiebreak
  so repeated calls against the same data always return the same row. Under
  migration 023 this ordering only matters for legacy pre-023 rows that
  already violated the one-founder invariant before the index existed; going
  forward there is at most one row to pick from.
- **`find_clan_founder` also filters `p.is_deleted = false`** on the founder's
  person row — a soft-deleted founder is treated as "no founder," not "old
  founder still roots the tree."

## Consequences

- **đời (generation) activates.** Once an admin designates a founder via
  `PUT /clans/me/founder`, `GET /tree` (no `root_person_id`) roots there,
  and every reachable node's graph-computed đời (ADR-012) populates instead
  of returning `null` everywhere. This is the practical unblock for the
  entire đời feature, which was previously unreachable in practice per H3.
- **Undesignated clan is an onboarding state, not an error state.** A clan
  with no founder yet 404s `GET /tree` (no `root_person_id`) with
  `clan_founder_not_found`. Clients must treat this as "prompt the admin to
  designate a thủy tổ," not a broken-tree state — see
  `frontend-integration-guide.md` §5.1 and `error-codes.md`.
- **Soft-deleting the founder re-404s the tree until restore or
  re-designation.** Because `find_clan_founder` filters `is_deleted = false`
  on the founder person, soft-deleting the currently-designated founder makes
  the clan founder-less again (`GET /tree` → 404 `clan_founder_not_found`).
  Delete/restore never touch `is_founder` on the membership row — the flag
  survives the soft-delete untouched. So **restoring the same person alone
  re-roots the tree automatically**: `PersonCommandHandler.restore` only
  flips `persons.is_deleted` back to `false`, and on the next `GET /tree`,
  `find_clan_founder`'s `is_deleted = false` filter matches that membership
  row again with no further write. Re-designation via
  `PUT /clans/me/founder` is only needed to **change** who the founder is
  (i.e. the deleted founder will not be restored, or an admin wants someone
  else to root the tree instead).
- **The export's multi-founder ordered-walk tolerance is now structurally
  unreachable against a live schema** (kept for pre-023 archives/robustness —
  see the rewritten `test_clan_export_json` single-founder pin). Migration
  023's partial unique index makes 2+ live founder rows for one clan
  impossible going forward, so `rest-exports-api.md`'s "when multiple
  founders exist, deterministic ordering decides which founder's tree wins"
  language now only describes how the export serializer would behave against
  already-corrupt legacy data (pre-023 databases, or a downgrade), not a
  reachable state on any current clan. The export serializer keeps the
  tolerance rather than assuming a schema invariant it doesn't itself enforce
  — belt-and-suspenders for an archival/lossless code path.
- **`save_with_membership(is_founder=...)` plumbing remains** in the
  repository layer but stays unreachable via the API — `PersonCreateRequest`
  has no `is_founder`/founder field, so no client request can set it on
  create. If an internal caller (a script, a future migration, a batch
  import) ever passed `is_founder=True` into a clan that already has a live
  founder, the 023 index rejects the write as `23505` → the standard 409
  `conflict` envelope, never a silent second founder and never a 500.
- **The ordered `swap_founder` repository method exists** (clear-then-set as
  two explicitly sequenced `UPDATE` statements, not two ORM attribute
  mutations resolved by a single flush) because Postgres cannot defer a
  **partial** unique index (`DEFERRABLE` applies to constraints, and
  constraints cannot be partial — only indexes can), and SQLAlchemy's
  dirty-object flush order is unspecified. A first draft that mutated both
  the outgoing and incoming membership's `is_founder` attribute and let the
  UoW's single flush order them deadlocked or tripped
  `uq_clan_memberships_one_founder` on roughly 80% of swap-test runs, because
  the flush sometimes emitted the new founder's `SET is_founder = true`
  before the old founder's `SET is_founder = false` committed, momentarily
  presenting two live founders to the immediate partial index. Two explicit,
  ordered `session.execute()` statements (clear all, then set the target)
  guarantee the CLEAR is visible before the SET is attempted, closing the gap.
- Migration 023's precheck fails the migration loudly (listing every clan
  with >1 live founder) if legacy data already violates the invariant, per
  house precedent (015/021/022) — no silent repair.

## Alternatives considered

- **Founder-set management (allow multiple flagged founders, pick one by
  rule at read time)** — rejected: this is exactly the H3 state that was
  already broken (nondeterministic `LIMIT 1`), and a "pick one of several" read
  rule doesn't match the domain concept — a clan has exactly one thủy tổ.
  Modeling it as a set only reintroduces the ambiguity this ADR closes.
- **`is_founder` settable on person create (`PersonCreateRequest` gains a
  field)** — rejected: conflates person creation with clan-root designation
  and reopens the concurrent-create race migration 023 exists to prevent (two
  admins creating "the first person" concurrently, each flagged as founder,
  racing the same partial unique index but with no clear "corrected" outcome
  — a create that loses the race just fails, instead of the admin explicitly
  correcting a mistaken designation later via swap). A dedicated
  designate/correct endpoint keeps founder assignment an explicit,
  auditable, always-correctable admin action, decoupled from person
  creation.
