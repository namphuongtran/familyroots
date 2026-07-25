# RLS Layer-2 Activation — Phase 1 (runtime seam + `documents` live) — Design

**Date:** 2026-07-25
**Owner direction:** activate RLS layer-2 (SP-3 / ADR-008), pilot-first.
**Scope of THIS phase:** wire the runtime so request traffic runs under the non-bypass
`familyroots_app` role with a per-request clan GUC, and make **one** table (`documents`,
whose policy already exists) genuinely RLS-enforced end-to-end. NO other table's RLS is
enabled here. Later phases add tables one at a time.

## Why this is the risky one

RLS is inert today: migration 002 created `familyroots_app` (NOBYPASSRLS, NOLOGIN),
granted table CRUD, and added the `documents_clan_isolation` policy — but the app
connects as the privileged owner, so RLS never applies. Activating it wrong makes
**every query return zero rows** (or error). Hence: pilot one table, fail closed,
prove it two-sided through the real stack, keep the app layer as the primary defense.

## Mechanism (validated by the existing `test_rls_documents`)

Per request transaction, drop to the non-bypass role and set the clan GUC:

```sql
SET LOCAL ROLE familyroots_app;                       -- RLS now applies (txn-scoped)
SELECT set_config('app.clan_id', '<uuid>' , true);    -- txn-local clan context
```

`SET LOCAL` / `set_config(..., true)` are **transaction-scoped**, so they can't leak
across pooled connections (pgbouncer-safe). System paths (Alembic migrations, the
APScheduler jobs, the document-purge job) keep their privileged connection and do NOT
drop role — they legitimately bypass RLS (cross-clan/system writers).

### The ordering blocker and its resolution

`get_current_clan_id` → depends on `get_current_user` → depends on `get_db`. So the
request transaction **begins during `get_current_user`'s first query, before `clan_id`
is known** — a begin-time `SET LOCAL app.clan_id` cannot know the clan. Resolution:

1. **Drop role at transaction begin, not the GUC.** A SQLAlchemy `after_begin` event on
   the *request* session issues `SET LOCAL ROLE familyroots_app` as the first statement
   of every request transaction. `get_current_user`/`get_current_clan_id` then run under
   `familyroots_app` — fine, because in Phase 1 they only touch NON-RLS tables
   (`user_profiles`, `user_clan_roles`).
2. **Set the clan GUC the moment it is known.** `get_current_clan_id`, right after it
   resolves `resolved_clan_id`, issues
   `await db.execute(select(func.set_config('app.clan_id', str(clan_id), True)))`
   on the same session/transaction. Because `documents` is only ever queried by the
   *handler* (which runs after all dependencies resolve), the GUC is set before any
   RLS-table access.
3. **Default-deny for no-clan requests.** If a request never sets `app.clan_id`
   (unauthenticated, or a non-clan route), the policy's
   `nullif(current_setting('app.clan_id', true), '')::uuid` is NULL → zero rows. Those
   routes don't touch `documents`, so this is invisible — but it's fail-closed, not
   fail-open, which is the whole point.

### Request vs system session split

The `after_begin` role-drop must fire ONLY for request sessions, never for the
scheduler/purge/migration sessions (which must stay privileged). Two clean options
(pick in review):
- **(A) Separate sessionmakers.** `AsyncRequestSessionLocal` (role-dropping event
  attached) used by `get_db`; the existing `AsyncSessionLocal` (no event) used by
  system code. Explicit, hard to get wrong.
- **(B) One sessionmaker, per-session opt-in flag.** `get_db` marks
  `session.info["rls"] = True`; the `after_begin` event checks the flag. Less
  duplication, but the flag must be set before the first query.

Recommendation: **(A)** — an explicit request-vs-system engine/session split is the
least error-prone for a fail-closed security boundary, and it documents intent.

## Grant completeness (a "silent gap" per ADR-008)

Migration 002 granted table CRUD + default privileges + schema USAGE, but NOT:
- **`USAGE, SELECT` on all sequences** — needed if any table uses a serial/identity
  default (audit? verify; PKs are client-side `uuid4`, so likely none — but grant
  defensively so a future serial column doesn't break under the role).
- **`EXECUTE` on all functions** — `familyroots_app` must call `find_relationship_path`,
  `get_descendants_flat`, `f_unaccent`, the lunar/tree functions, etc. Without this,
  every tree/search query fails under the role. **This is the most likely activation
  break** and is covered by the phase's smoke test.

The activation migration adds these grants (+ `ALTER DEFAULT PRIVILEGES` for future
sequences/functions), idempotently.

## Startup / CI assertion (RLS must not be silently inert)

- A startup check (or a CI test) opens a request-style session, `SET LOCAL ROLE
  familyroots_app`, and asserts the effective role is **not** superuser and does **not**
  bypass RLS (`SELECT current_setting('is_superuser')` = `off`; a seeded cross-clan
  `documents` row is invisible without the matching GUC). If the role can bypass, the
  whole layer is false security — fail startup / fail CI loudly.

## Tests (real-DB; the proof this is REAL, not inert)

1. **End-to-end two-sided through the app stack:** two clans each with a document;
   `GET /documents` (and `GET /documents/{id}`) as clan A returns only A's, as clan B
   only B's — with RLS as the enforcing layer (verified by also asserting the row is
   invisible at the DB level under the role without the app-layer filter). Extends the
   existing `test_rls_documents` from a raw-connection proof to a through-the-handler
   proof.
2. **Default-deny:** a request/session with no `app.clan_id` sees zero `documents`.
3. **System path still bypasses:** the document-purge job (system session) still sees
   all clans' documents (it must, to purge platform-wide).
4. **Grant smoke test:** under `familyroots_app`, a representative query that calls a
   SQL function (e.g. a tree/search path) succeeds — pins the EXECUTE grants.
5. **Non-bypass assertion** (above).
6. **RLS-coverage enumeration (CI guard):** a test listing every table with RLS enabled
   and asserting each has a policy + the role has the needed grants — so Phase 2+ can't
   enable RLS on a table without a policy (a silent lockout) or forget a grant.

Existing suites stay green: the test conftest connects as the privileged role and seeds
directly (bypass), so pre-existing tests are unaffected; only the new RLS tests drop
role.

## What this phase does NOT do

- Does NOT enable RLS on any table other than `documents`.
- Does NOT change handler signatures, the app-layer clan filters (they remain primary),
  or any API contract.
- Does NOT require a second DB credential / `SYSTEM_DATABASE_URL` (the `SET LOCAL ROLE`
  approach keeps the single connection; the "system vs request" split is at the session
  layer, not the credential layer). If production later prefers a dedicated login role,
  that's an ops follow-up, not a code dependency.

## Rollback

Trivial and safe: `ALTER TABLE documents DISABLE ROW LEVEL SECURITY` (RLS off → the app
layer still fully protects), and/or stop dropping role in `get_db`. No data change.

## Migrations & ADR

- New migration `026_rls_activation_grants` — the completeness grants (sequences,
  functions, default privileges) for `familyroots_app`. (The `documents` policy + role
  already exist from 002; `documents` RLS is already `ENABLE`d — activation is the
  runtime seam, not a table change, so Phase 1 may need no table migration beyond
  grants. Verify `documents` RLS is `ENABLE`d in 002 and add the `ENABLE` only if not.)
- Update **ADR-008** status from "pilot only" to "Phase-1 active (documents live);
  rollout in progress," recording the `SET LOCAL ROLE` seam + the ordering-blocker
  resolution + the request/system session split decision.

## Phase plan (for context; only Phase 1 in this PR)

1. **Phase 1 (this PR):** runtime seam + grants + `documents` live + the six tests + the
   non-bypass/coverage guards.
2. **Phase 2+:** enable RLS + add a policy per remaining clan-scoped table, one small
   reviewed PR at a time — `clans`/`clan_memberships`, `persons` (M:N via a
   `clan_memberships` subquery — needs the perf check ADR-008 flagged), `marriages`,
   `parent_child`, `events`, `branches`, `audit_logs`, `clan_invitations`,
   `user_clan_roles`. Each phase: enable + policy + two-sided test + coverage-test update.
3. **Final:** consider `FORCE ROW LEVEL SECURITY` (so even the table owner is subject)
   once every table is covered and the system paths are proven to use the privileged
   session — a separate hardening decision.
