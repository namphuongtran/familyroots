# Design / Spike: Row-Level Security (RLS) as Defense-in-Depth Layer-2

- **Date:** 2026-06-28
- **Status:** Design — for review. No code yet. (SP-3C)
- **Scope:** `backend/` PostgreSQL access path + a piloted RLS rollout.
- **Relationship to other work:** App-layer clan isolation is already the **primary, rigorously-tested** mechanism (SP-2B sealed every read path with two-sided tests; the repository contract requires `clan_id` on every clan-scoped read). RLS here is a **second layer** that catches a future missed filter at the database boundary. It must never become the *only* thing standing between clans.

## Why this is non-trivial (the core obstacle)

RLS only takes effect when the connecting Postgres role is **not** a superuser and does **not** have `BYPASSRLS`. Today:

- **Local/CI dev** connects as `postgres` (the docker superuser) → **bypasses RLS entirely**.
- **Supabase prod** connects via `DATABASE_URL` whose role (Supabase's `postgres`) also bypasses RLS. (Supabase's `authenticated`/`anon` roles enforce RLS, but the backend does not use the PostgREST path — it talks SQLAlchemy directly.)

So "turn on RLS" without changing the connection role is **false security**: policies exist but never apply. The real work is a **connection-model change** plus a **per-request context injection** mechanism. That is the riskiest part of the whole production-hardening effort — a wrong move can make *every* query return zero rows (default-deny) or error.

## Goals

1. A dedicated, non-privileged DB role the app connects as for **request-scoped** queries, under which RLS is enforced.
2. Per-request injection of the caller's active clan (and user) so policies can scope rows — working identically on **plain Postgres (dev/CI)** and **Supabase (prod)**.
3. RLS policies that mirror the app-layer model exactly (clan-owned via `clan_id`; edges via `created_by_clan_id`; persons via `clan_memberships`).
4. A **piloted** rollout (one table first) so the "RLS breaks everything" failure mode is caught on a small surface, not the whole schema at once.
5. A **privileged/system path** for migrations and the cross-clan scheduler job that legitimately must bypass RLS.

## Non-goals

- Replacing the app-layer isolation (it stays the primary mechanism and the source of truth).
- Changing the schema or the domain model.
- Adopting Supabase's PostgREST/`auth.uid()` path (we stay on SQLAlchemy).

---

## Proposed architecture

### 1. Two connection contexts

| Context | Role | RLS | Used by |
|---|---|---|---|
| **Request** | `familyroots_app` (NOLOGIN-inheritable, NO BYPASSRLS, table CRUD grants) | **enforced** | the FastAPI request path (`get_db` session) |
| **System** | owner / privileged role (current `postgres`/Supabase role) | bypassed | Alembic migrations, the anniversary scheduler (cross-clan by design), any admin/maintenance task |

Two DSNs: `DATABASE_URL` (request, `familyroots_app`) and `SYSTEM_DATABASE_URL` (migrations + scheduler). The scheduler already runs as a separate code path (`AsyncSessionLocal` in `services/scheduler.py`) and could use a system engine; migrations already run via `env.py` and would use the system DSN.

### 2. Per-request context via app-specific GUCs (portable)

Two candidate mechanisms:

- **(A) Supabase-native:** `SET LOCAL request.jwt.claims = '<jwt>'; SET LOCAL ROLE authenticated;` and policies use `auth.uid()`/`auth.jwt()`. **Rejected as the primary:** the `auth` schema, the `authenticated` role, and the `request.jwt.claims` convention **do not exist on plain Postgres** (local/CI), breaking dev/prod parity and the existing real-DB test suite.
- **(B) App GUCs (proposed):** at transaction start, `SET LOCAL app.user_id = :uid; SET LOCAL app.clan_id = :clan_id;` and policies read `current_setting('app.clan_id', true)`. Works identically on plain Postgres and Supabase, matches the portable choice we already made for provisioning.

`SET LOCAL` is **transaction-scoped**, so it is safe with pgbouncer transaction pooling and cannot leak across pooled clients (unlike a session-level `SET`). It must be set **inside** the request's transaction.

**Default-deny is mandatory.** `current_setting('app.clan_id', true)` returns `NULL` when unset (e.g., a code path that forgot to set context). Every policy's `USING`/`WITH CHECK` must treat NULL as "no access" — e.g. `clan_id = nullif(current_setting('app.clan_id', true), '')::uuid` yields `clan_id = NULL` → false → zero rows. So a missed context injection fails closed, never open.

### 3. Where context is set in code

`get_current_clan_id` (and `get_current_user`) already resolve the active clan/user per request. The plumbing:

- A request dependency stores `(user_id, active_clan_id)` in a `ContextVar` (set after `get_current_clan_id` validates membership).
- `get_db` (or a thin wrapper) issues `SET LOCAL app.user_id = ...; SET LOCAL app.clan_id = ...;` at the start of the session's transaction, reading the ContextVar.
- For endpoints with no active clan (e.g. `/me`, onboarding, login), context is set with the user only (clan unset) — those tables either aren't RLS-scoped or use the user GUC.

> **Open design point:** the cleanest injection seam — `get_db` setting GUCs from a ContextVar, vs. an explicit `uow.bind_context(user_id, clan_id)`. The ContextVar approach keeps handler signatures unchanged but introduces request-scoped global state; the explicit approach is more visible but threads context through more call sites. **Recommendation: ContextVar + `get_db` SET LOCAL**, because the UoW/session is created per request and the dependencies already compute the values.

### 4. Policy model (mirrors the app-layer rules)

| Table(s) | Policy `USING` (read) | Notes |
|---|---|---|
| `branches`, `documents`, `events`, `clan_settings`, `clan_memberships`, `user_clan_roles`, `change_requests`, `notification_log` | `clan_id = nullif(current_setting('app.clan_id', true), '')::uuid` | Simple clan-owned. |
| `marriages`, `parent_child` | `created_by_clan_id = nullif(current_setting('app.clan_id', true), '')::uuid` | Edges write-gated by origin clan; strict isolation = read by origin clan. |
| `persons` | `EXISTS (SELECT 1 FROM clan_memberships cm WHERE cm.person_id = persons.id AND cm.clan_id = nullif(current_setting('app.clan_id', true),'')::uuid)` | M:N — a clan sees persons that are members of it. Subquery per row → **index `clan_memberships(person_id, clan_id)` required** (already present from SP-1). Performance to validate in the pilot's successor. |
| `clans` | `id = nullif(current_setting('app.clan_id', true),'')::uuid` OR membership exists | The active clan + (optionally) clans the user belongs to. |
| `user_profiles` | `id = nullif(current_setting('app.user_id', true),'')::uuid` (+ co-member visibility if needed) | Mostly self; co-member visibility is a product question. |

`WITH CHECK` clauses mirror `USING` for writes, plus the existing write-gate (`created_by_clan_id`) semantics for edges.

### 5. Pilot-first rollout (de-risk)

**Phase 0 — pilot on `documents` only** (simplest clan-owned table, low blast radius):
1. Create the `familyroots_app` role + grants (in a dedicated additive migration; does NOT touch baseline tables).
2. `ALTER TABLE documents ENABLE ROW LEVEL SECURITY; FORCE ROW LEVEL SECURITY;` + the clan policy.
3. Add the ContextVar + `get_db` `SET LOCAL` plumbing.
4. Add `SYSTEM_DATABASE_URL` for migrations + scheduler.
5. **Test (integration):** connect as `familyroots_app`, set `app.clan_id = A` → see only clan A's documents; set `B` → none of A's; **unset → zero rows (default-deny)**. Confirm the role does NOT bypass (negative test: a row from clan B is invisible even via a raw `SELECT *`).
6. Run the full suite under the new request-role connection to catch anything that breaks.

**Phase 1+ — expand table-by-table** (edges, then persons with the M:N policy + perf check, then the rest), each with the same two-sided + default-deny test, only after the pilot proves the plumbing.

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| App connects as a BYPASSRLS role → RLS silently inert (false security) | A startup/CI assertion: `SELECT current_setting('is_superuser')` is `off` AND `rolbypassrls` is false for the request role; a test that a cross-clan row is invisible. |
| Missed context on a code path → policy NULL → **open** access | Default-deny via `nullif(...,'')::uuid` so NULL → false → **closed**, not open. Pilot test asserts unset-context = zero rows. |
| Connection pooling leaks context across clients | Use `SET LOCAL` (transaction-scoped) only; never session `SET`. Safe with pgbouncer transaction mode. |
| Migrations/scheduler need cross-clan | Separate `SYSTEM_DATABASE_URL`/privileged role; they never use the request role. |
| `persons` M:N subquery perf | Index `clan_memberships(person_id, clan_id)` (present); benchmark in the persons phase; consider a security-definer helper if needed. |
| Grants drift (new tables added without grants/policies) | A test enumerating tables with RLS disabled / without grants; CI guard. |
| `familyroots_app` role missing in an environment | Role-provisioning migration is idempotent (`DO $$ ... IF NOT EXISTS`); document the Supabase/Render role setup. |

## Testing strategy

- **Role property test:** the request role is non-superuser, `NOBYPASSRLS`.
- **Pilot isolation test (documents):** two clans seeded (system role); as request role with `app.clan_id=A` → only A's rows; `=B` → none of A's; unset → none (default-deny); a direct `SELECT *` cannot see cross-clan rows.
- **App-path regression:** the full suite runs with the request-role engine; existing app-layer tests still pass (RLS is invisible when context matches).
- **No-context fail-closed:** an endpoint reached without context set returns empty/forbidden, never cross-clan data.

## Rollout / rollback

- Each phase is an **additive migration** (role, `ENABLE RLS`, policies) — no baseline-table change. Rollback = `DISABLE ROW LEVEL SECURITY` + drop policies (RLS off → app-layer still protects). Reverting the connection-role change restores the prior behavior.

---

## Open questions for sign-off (before any implementation)

1. **GUC strategy:** app-specific `app.clan_id`/`app.user_id` (proposed, portable) vs. Supabase-native `request.jwt.claims`? (Recommend app-specific for dev/prod parity.)
2. **Role provisioning:** create `familyroots_app` + grants via an Alembic migration (idempotent), or as an ops/Supabase-dashboard step? (Recommend migration for reproducibility; confirm Supabase allows creating a custom role.)
3. **System path:** a separate `SYSTEM_DATABASE_URL` for migrations + scheduler (proposed), or `SET ROLE` toggling on one connection? (Recommend separate DSN — clearer, no per-query role juggling.)
4. **Context seam:** ContextVar + `get_db` `SET LOCAL` (proposed) vs. explicit `uow.bind_context(...)`?
5. **Pilot table:** `documents` (proposed) — agree, or prefer a different first table?
6. **user_profiles / clans visibility:** self-only, or co-member visibility? (Product decision; affects those policies.)
7. **Effort/risk appetite:** given app-layer isolation is already rigorous + tested, is the full table-by-table RLS rollout worth it now, or do we ship the pilot (documents) as proof + defense-in-depth and expand later?

## Recommendation

Proceed in this order once the open questions are signed off: **role + system DSN + ContextVar/`get_db` plumbing + `documents` pilot + its isolation tests** as the first, self-contained PR. Treat the table-by-table expansion as subsequent, individually-reviewed phases. Keep the app-layer the primary guarantee throughout — RLS is the seatbelt, not the brakes.
