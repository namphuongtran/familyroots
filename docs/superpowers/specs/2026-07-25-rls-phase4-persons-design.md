# RLS Layer-2 Phase 4 — `persons` (M:N membership isolation) — Design

**Date:** 2026-07-25
**Owner direction:** design + implement persons-RLS (approved), present the design +
decisions for approval before coding.
**Why persons is different:** it's the only M:N table (a person belongs to clans via
`clan_memberships`; `persons.created_by_clan_id` is a nullable *origin*, not membership),
and — unlike documents/events/branches/edges — it is read by two **cross-clan** flows
that have no clan context, so a naive policy would break them. This phase therefore
needs small app-code changes, not just a migration.

## The policy (per-command, not one ALL policy)

A single `ALL` policy can't satisfy both create and shared-person edits (see below), so
persons uses per-command policies keyed on the `app.clan_id` GUC:

- **SELECT** `USING (EXISTS (SELECT 1 FROM clan_memberships m WHERE m.person_id =
  persons.id AND m.clan_id = <GUC>))` — the read backstop. A person is visible to a
  request only if they are a **member** of the active clan. This is the primary
  defense-in-depth value: a missed application `clan_memberships` join can't leak
  cross-clan person PII.
- **INSERT** `WITH CHECK (created_by_clan_id = <GUC>)` — a request may only create a
  person owned by its own clan (the app always sets `created_by_clan_id = clan_id`, so
  this is a free backstop that works with the create order below).
- **UPDATE** `USING (<membership subquery>) WITH CHECK (true)` — a request may update a
  person it can see (a member), with **no** restriction on the post-image. This is
  deliberate: it must not break (a) soft-delete/restore (an UPDATE), or (b) editing a
  **shared** person whose `created_by_clan_id` is a *different* clan than the editor
  (the app authorizes edits by membership via `get_in_clan`, so a `created_by_clan_id =
  GUC` check here would wrongly reject a legitimate shared-person edit).
- **DELETE** `USING (<membership subquery>)` — symmetric (persons are soft-deleted via
  UPDATE, so this is a safety default).

### Why not `WITH CHECK = membership` on INSERT

`PersonCommandHandler.create` → `save_with_membership` adds the **person row first**,
then the `clan_memberships` row (`person_repository.py:227,237`), flushed together. A
membership-subquery `WITH CHECK` on the person INSERT evaluates **before** the membership
row exists → the insert fails. `created_by_clan_id = GUC` sidesteps this (the column is
set at insert time).

## The cross-clan readers (the app-code change)

Two flows read `persons` **without** a clan GUC and would default-deny to zero under
persons-RLS. Both are legitimately cross-clan / platform, so they run on the **privileged
system session** (bypass RLS), exactly like the scheduler/purge already do:

1. **Identity claims** (`claim_repository.get_live_person`/`get_person`, used by
   submit/cancel/approve/reject/unlink/prelink). A claimant claims to *be* a person in
   some clan and has no membership there yet — the lookup is a global-by-id resolution.
   `claim_handlers` write only `identity_claims` / `user_clan_roles` / `user_profiles` /
   `audit_logs` — **none of which have RLS** — so running the claim handlers on a system
   session is safe and semantically correct (a cross-clan identity flow).
2. **Platform-admin metrics** (`platform_admin_query_port` `total_members` counts all
   persons cross-clan). Super-admin endpoints are not clan-scoped; they already read
   platform-wide. Run the platform-admin query/command handlers on the system session.

**Mechanism:** add a `get_system_db` FastAPI dependency (yields `AsyncSessionLocal()` —
the existing non-RLS session) and wire `get_claim_command_handler`,
`get_claim_query_handler`, and the two platform-admin handlers to it instead of `get_db`.
No handler logic changes. Everything else (person list, tree, timeline, export, person
CRUD, relationships) stays on `get_db` (request session, GUC set) — verified clan-scoped.

## What stays on the request session (verified safe)

`person_repository` list/get_in_clan/batch, `person_query_port` timeline,
`tree_repository` (person_in_clan, focus, ancestors), `export_query_port` persons, and
the tree SQL functions (which JOIN `persons`) all filter by a `clan_memberships` join /
`created_by_clan_id = clan` = the request's clan = the GUC — so persons-RLS is **redundant
with their existing filter**, results unchanged. The tree does not truncate **iff every
edge/marriage-referenced person is a member of that clan** — which holds because persons
enter a clan only via `save_with_membership` (create) or an explicit membership add; a
married-in spouse is an existing person (created with a membership) before being married.
Verified by a test (full tree returns under the seam).

## Perf

The SELECT/UPDATE/DELETE membership subquery runs per candidate row. It's backed by the
unique index `uq_clan_memberships_person_clan (person_id, clan_id)` and
`idx_clan_memberships_person` — an index-only `EXISTS`. Person list is paginated (≤ limit
rows); the tree is bounded by clan size. A perf test EXPLAINs the person-list query under
the policy and asserts an index scan on `clan_memberships` (no seq scan), matching the
trigram-index-test pattern.

## Migration `029_rls_persons`

`ENABLE ROW LEVEL SECURITY ON persons` + the four per-command policies. Reversible (drop
policies + disable). No schema change. Grants already exist (002 + 026).

## Tests (real-DB, through the seam)

1. **Read isolation:** a person who is a member of clan A only is visible under GUC=A,
   invisible under GUC=B (naked `SELECT` under the seam).
2. **A shared person** (member of A and B) is visible under both.
3. **Create works** under the seam: `save_with_membership` inserts person+membership
   under GUC=A → succeeds (INSERT WITH CHECK `created_by_clan_id=A=GUC` passes despite the
   membership row being added after).
4. **Shared-person edit works:** update a person whose `created_by_clan_id` = clan A while
   under GUC=B (B is a member) → succeeds (UPDATE WITH CHECK is permissive) — proves the
   `created_by_clan_id=GUC` trap is avoided.
5. **Tree not truncated:** seed a clan tree (all members), `get_family_tree_flat` /
   ancestors under GUC=A return the full node set (a married-in spouse with a membership
   included).
6. **Claim submit works under persons-RLS:** driving `submit_claim` (system session) can
   still resolve the target person cross-clan → claim created (would default-deny if it
   used the request session).
7. **Platform metrics correct:** `total_members` counts all clans' persons (system
   session bypass), not zero.
8. **Default-deny:** no GUC on a request session → zero persons.
9. **Perf:** person-list EXPLAIN uses the `clan_memberships` index.
10. Coverage guard → `{documents, events, branches, parent_child, marriages, persons}`.

## Rollback

`RLS_ENABLED=false` (global) or `DISABLE ROW LEVEL SECURITY ON persons` + drop policies
(migration downgrade). The claim/platform handlers on the system session are correct
regardless of RLS state (they were previously on the request session which also worked
because RLS was inert there — no behavior change when RLS is off).

## Decisions embedded (for approval)

- **D1 — per-command policy** (SELECT/UPDATE/DELETE = membership; INSERT WITH CHECK =
  `created_by_clan_id = GUC`; UPDATE WITH CHECK = permissive). *Recommended* — the only
  form that keeps create, soft-delete, and shared-person edits working while isolating
  reads. Alternative (single ALL policy) breaks one of them.
- **D2 — cross-clan readers (claims + platform-admin) move to the system session.**
  *Recommended* — they are cross-clan flows that touch no RLS-enabled table except the
  `persons` lookups they must bypass. Alternative (a per-query bypass inside the request
  session) is more invasive and error-prone.
