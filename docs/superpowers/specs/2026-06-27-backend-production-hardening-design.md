# Design: Backend Production Hardening

- **Date:** 2026-06-27
- **Status:** Approved (design); pending implementation plans
- **Scope:** `backend/` (FastAPI / SQLAlchemy / PostgreSQL)
- **Driver:** Pre-`docker compose up` review surfaced schema↔model drift, broken
  flows (register, claim approve/reject), cross-clan data leaks, and several
  production-readiness gaps. Goal is correctness and long-term quality — no
  workarounds.

## Context

FamilyRoots is a pre-production Vietnamese genealogy platform. The backend follows
DDD + CQRS + hexagonal layering (see `backend/CLAUDE.md`, ADR-001). A review of the
Python backend found that the single Alembic migration (`001_initial.py`) has
diverged from the ORM models, two core flows crash or violate FK constraints, and
the documented "RLS layer-2" isolation does not actually run. The database is empty
and may be reset freely, so we can cut one clean baseline migration rather than
chained upgrade migrations.

## Locked architectural decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Baseline migration | Design-first; cut **one** clean baseline. DB empty, reset freely. | No backward-compat churn; highest quality. |
| 2 | Cross-clan visibility | **Strict clan isolation.** A clan sees only its own persons + relationships. | Matches the "communities coexist safely" mandate. Cross-clan marriage links are out of scope for now. |
| 3 | Isolation enforcement | App-layer is the rigorous primary mechanism now; **Postgres RLS as defense-in-depth layer-2 in SP-3.** Remove the false RLS claim immediately. | App-layer is testable and portable; RLS is a heavy add fighting the M:N person model + pooling. |
| 4 | User provisioning | **App-layer idempotent `ensure_profile()`**, in-transaction, at every entry path. | Portable across local plain Postgres and Supabase (local has no `auth.users`). `user_profiles.id` has no FK to `auth.users`. |
| 5 | Durable events | **Defer** outbox/Redis (ADR-004 future). Fix audit-integrity bug now. | `audit_logs` is already durable in-transaction; no separate worker exists yet. Adding an outbox later is an additive migration. |
| 6 | Invitation | **Email-targeted token** + expiry; coexists with self-request-join; MVP returns the link (no email infra yet). | Safest for family data; preserves discovery path; avoids deliverability work. |

## Sub-project decomposition (sequential)

Each sub-project gets its own implementation plan. **Order is strict: SP-1 → SP-2 → SP-3.**

```
SP-1  Schema baseline & data-model correctness   (foundation — everything depends on it)
SP-2  Identity, access & tenant isolation         (app-layer correctness + invitation feature)
SP-3  Platform & production hardening             (ops readiness + RLS layer-2)
```

---

## SP-1 — Schema baseline & data-model correctness

Pure schema/model layer. Output: `alembic upgrade head` builds a schema that matches
the ORM models exactly, and the app boots and runs core flows.

### Tasks

1. **Eliminate all model↔migration drift.** Confirmed mismatches:
   - `persons`: model `created_by_clan_id` (`app/models/person.py:20`) vs migration
     `origin_clan_id` (`migrations/versions/001_initial.py:69`, index l.140). The
     entire codebase uses `created_by_clan_id`. → migration must use
     `created_by_clan_id`.
   - `identity_claims`: model `reviewer_note` (`app/models/identity_claim.py:42`) vs
     migration `reasoning` (`001_initial.py:760`). → migration must use
     `reviewer_note`; drop the dead `reasoning` column.
   - Full column/index/constraint audit of all 18 model files vs the migration.
2. **Enum strategy → `String + CHECK`.** Drop the 5 PG enum types
   (`gender_type` l.82, `document_type` l.443, `event_type` l.507, `clan_role`
   l.700, `notification_status` l.897) and represent these columns as `String` with
   `CHECK` constraints — matching the current ORM models (which already declare
   `String`). PG enums are hard to evolve (`ALTER TYPE` cannot remove values, and
   adding values is transaction-hostile in older PG); the domain layer remains the
   source of truth for valid values.
3. **Add `naming_convention` to `Base.metadata`** (`app/models/base.py`) using the
   standard Alembic convention (`ix`/`uq`/`ck`/`fk`/`pk`). Reconcile every
   model-declared constraint name (`uq_person_clan`, `uq_user_clan`,
   `uq_parent_child_edge`, …) with the regenerated migration so future
   `--autogenerate` runs produce empty diffs.
4. **Cascade vs soft-delete.** Change the `persons` FK on `marriage`
   (`marriage.py:23,28`) and `parent_child` (`parent_child.py:34,39`) from
   `ON DELETE CASCADE` to **`ON DELETE RESTRICT`** — persons are soft-deleted
   (ADR-006), so a hard delete must not silently destroy lineage edges. Document the
   policy alongside ADR-006.
5. **Actor columns stay FK-free.** `created_by` / `updated_by` / `deleted_by` /
   `invited_by` / `reviewed_by` / `actor_id` / `requester_id` remain indexed `UUID`
   with **no FK** to `user_profiles` — they reference Supabase identity and audit
   rows must outlive user deletion. This is a deliberate, documented choice.
6. **Invitation schema additions** to `clan_invitations` (table already has
   `clan_id`, `email`, `role`, `invited_by`, `token`, `expires_at`, `accepted_at`):
   - add `status String` with CHECK (`pending` | `accepted` | `revoked` | `expired`)
   - add `accepted_by UUID` (nullable; the user who accepted)
   - add partial unique index: one `pending` invite per `(clan_id, email)`.
7. **Regenerate one clean baseline `001_initial.py`** via `alembic revision
   --autogenerate` (models are now the source of truth and aligned), then **verify
   round-trip**: `upgrade head` → `downgrade base` → `upgrade head` succeeds. Fix the
   incomplete `downgrade()` (currently never drops `identity_claims`).
8. **Make `migrations/env.py` model import explicit.** It currently names a subset
   of models but still registers all tables because importing `app.models` runs the
   package `__init__` (which imports all 18). Replace with `import app.models` (or
   `from app.models import *`) so intent is unambiguous and robust to refactors.

### Success criteria (SP-1)
- `alembic upgrade head` on a fresh DB creates a schema with zero drift from models.
- `alembic revision --autogenerate` immediately after produces an **empty** diff.
- `upgrade → downgrade → upgrade` round-trips cleanly.
- A smoke query against `persons` / `identity_claims` succeeds (no `UndefinedColumn`).

---

## SP-2 — Identity, access & tenant isolation

App-layer correctness, the new-user lifecycle, isolation enforcement, auth
hardening, and the invitation feature. Depends on SP-1.

### 2.1 User provisioning (root-cause fix for the register FK violation)
- Add an idempotent `ensure_profile(user_id, email, full_name, ...)` in the auth
  application layer that upserts a `user_profiles` row.
- Call it **in the same UoW transaction, before any insert referencing `user_id`**,
  at: `register` (`app/application/auth/handlers.py`), `onboard_authenticated_user`,
  and the request-time auth dependency (replacing/normalizing the lazy
  `ensure_user_profile` in `app/core/security.py:86-123`).
- Make clan creation + role assignment in `_assign_clan_membership` atomic (single
  commit) so a failure cannot leave an admin-less orphan clan
  (`handlers.py:110-146`).

### 2.2 Claim approve/reject correctness (ADR-007 compliance)
- Replace the non-existent `self._db` references
  (`app/application/person/claim_handlers.py:174-177, 214-217`) with
  `self._repo` / `self._uow`.
- Route approve/reject through **UoW + domain events** (emit `IdentityClaim*`
  auditable events) instead of manual audit-row writes, consistent with the clan
  handlers and ADR-007.
- Add a "list my own claims" read endpoint so a user can see their claim status.

### 2.3 Tenant isolation — make `clan_id` a mandatory contract
- **Repository contract:** every clan-scoped read method takes `clan_id` and filters
  on it. Audit every `*_repository.py` / `*_query_port.py`.
- Confirmed leaks to fix:
  - `relationship_repository.get_by_id` for Marriage (l.130) and ParentChild
    (l.149) — add `clan_id`, filter `created_by_clan_id`; wire through the query
    handlers and the `GET /relationships/...` routes (which already inject but
    ignore `clan_id`).
  - `person_query_port.get_marriages` / `get_parent_child_links`
    (`person_query_port.py:31-49`) — scope by clan.
  - `claims.list_clan_claims` (`app/api/v1/claims.py:44-62`) — authorize against the
    **path** `{clan_id}` (or re-verify in the handler), not just the header clan.
- **Architectural isolation test:** a test asserting that every clan-scoped read
  rejects or excludes cross-clan data (acts as a regression guard for the contract).

### 2.4 RBAC consistency
- `update_person` PATCH (`app/api/v1/persons.py:337`): change `RequireViewer` →
  `RequireEditor`. Keep the "viewer may edit their own linked person, whitelisted
  fields" carve-out, but make it explicit and intentional in the handler
  (`app/application/person/handlers.py:90-109`), not a side effect of a loose route
  guard.
- Sweep all routers for consistent role gates on mutating endpoints.

### 2.5 Auth hardening
- Add `issuer` validation to `jwt.decode` (`app/core/security.py:64-69`):
  `issuer=f"{SUPABASE_URL}/auth/v1"`.
- Implement real **logout** (`app/api/v1/auth.py:77-80`): revoke the Supabase
  session/refresh token via the admin client instead of returning a no-op message.
- Normalize DI: `refresh_token` and `update_me` routes should resolve handlers via
  the composition root, not construct `SupabaseAuthService()` inline.
- Remove the unused `SUPABASE_JWT_SECRET` config (dead HS256 path) or wire it
  intentionally — decide and document; default is to remove.

### 2.6 Audit integrity
- `InMemoryEventDispatcher` (`app/infrastructure/event_dispatcher.py:47-53`) must
  **re-raise** handler exceptions so a failed `AuditLogHandler` write aborts the
  business commit (`app/infrastructure/unit_of_work.py:56`). Audit is part of the
  same transactional unit; it must not be silently dropped.

### 2.7 Invitation feature (email-targeted, MVP)
Full hexagonal slice (domain entity/port → application handlers → infrastructure
repository → API routes):
- **Create** (admin, `RequireAdmin`): input `email` + `role`; generate a
  cryptographically random `token`; store `clan_invitations` row with
  `status=pending`, `expires_at = now + N days` (config); **return the accept link**
  (no email sent in MVP). Reject if a `pending` invite already exists for
  `(clan_id, email)`.
- **Accept** (authenticated invitee, `POST /invitations/{token}/accept`): validate
  token exists, `status=pending`, not expired, and the **authenticated user's email
  matches the invite email**; then `ensure_profile()` + create
  `UserClanRole(role=<invited role>, is_approved=True)` and set
  `status=accepted`, `accepted_by`, `accepted_at` — all in one transaction.
- **Revoke / list** (admin): set `status=revoked`; list a clan's invitations.
- Expiry is computed/enforced on read (and reflected in `status`).
- **Coexists** with the existing self-request-join + admin-approve flow.

### 2.8 Documentation correction
- Update `docs/architecture/bounded-contexts.md` and
  `docs/architecture/domain-rules.md` to reflect **strict clan isolation** — persons
  and relationship edges are no longer described as "globally shared / visible across
  clans." Update any related multi-tenancy/RBAC docs and `backend/CLAUDE.md`'s RLS
  claim.

### Success criteria (SP-2)
- Register → create-clan and register → join-clan complete without FK errors.
- Claim approve/reject succeed and emit audit events through the UoW.
- Cross-clan read of a marriage/parent-child/claim by ID is denied; isolation test
  passes.
- A full invitation round-trip (create → accept → membership granted) works.
- Logout revokes the Supabase session.

---

## SP-3 — Platform & production hardening

Operational readiness and the RLS defense-in-depth layer. Depends on SP-1/SP-2.

1. **Config fail-fast** (`app/core/config.py`): when `APP_ENV=production`, reject
   `APP_SECRET_KEY == "change-me-in-production"` and force `APP_DEBUG=false`; change
   the default of `APP_DEBUG` to `false`.
2. **CORS + hosts** (`app/main.py:71-77`): explicit origin allowlist (no `*` with
   credentials); add `TrustedHostMiddleware`.
3. **Logging** (`app/core/logging.py`): call `configure_logging()` at startup; fix
   the JSON formatter to emit valid JSON (escape message); add basic secret
   redaction; stop `echo=APP_DEBUG` SQL value logging in non-dev.
4. **Generic exception handler**: register an `Exception` handler returning the
   standard `{ "error": { code, message, detail } }` envelope; never leak
   tracebacks.
5. **Run migrations on deploy**: container entrypoint runs `alembic upgrade head`
   before serving (and a compose migrate step), so a fresh DB is never served
   table-less.
6. **Scheduler** (`app/services/scheduler.py`): single-runner guarantee across
   replicas via a Postgres advisory lock (or external scheduler); close the dedup
   race in the anniversary job.
7. **Rate limiting** (`app/core/rate_limit.py`): Redis-backed sliding window;
   derive client IP from `X-Forwarded-For` behind the proxy; bound memory / evict
   idle IPs.
8. **Database** (`app/core/database.py`): `pool_pre_ping=True`; set
   `statement_cache_size=0` for asyncpg when behind pgbouncer transaction pooling.
9. **RLS layer-2** (defense-in-depth): inject the user's JWT/clan context onto the
   DB session per request (e.g. `SET LOCAL` of a GUC inside the UoW transaction) and
   add RLS policies in a **dedicated additive migration** (does not touch baseline
   tables). Persons require a policy keyed on `clan_memberships` (M:N).

### Success criteria (SP-3)
- App refuses to boot with insecure defaults under `APP_ENV=production`.
- Structured JSON logs emitted; unexpected errors return the envelope, not a stack
  trace.
- Fresh `docker compose up` yields a migrated, queryable DB with one command.
- Anniversary job fires once across N replicas.
- RLS denies cross-clan rows even if an app-layer filter is omitted.

---

## Testing strategy

- **SP-1:** migration round-trip test; `--autogenerate` empty-diff check; a DB-backed
  smoke test (currently tests mock DB rows, which is exactly why the drift went
  unnoticed — add at least one real-schema integration test).
- **SP-2:** unit tests for `ensure_profile` idempotency, claim approve/reject through
  UoW, invitation lifecycle; the cross-clan **isolation regression test**; auth
  issuer/logout tests.
- **SP-3:** config fail-fast tests; exception-envelope test; scheduler single-runner
  test (advisory lock); rate-limit behavior test.

## Out of scope / deferred

- Outbox table + Redis integration-event worker (ADR-004) — revisit when a separate
  worker service exists.
- Automated invitation email delivery — MVP returns the link.
- Cross-clan marriage links / shared-person visibility — excluded by the strict
  isolation decision; revisit as a dedicated feature if the product needs it.

## Affected areas (reference)

- Models / migration: `app/models/*`, `migrations/versions/001_initial.py`,
  `migrations/env.py`, `app/models/base.py`.
- Auth / identity: `app/application/auth/handlers.py`, `app/core/security.py`,
  `app/api/v1/auth.py`, `app/infrastructure/supabase_client.py`.
- Claims: `app/application/person/claim_handlers.py`, `app/api/v1/claims.py`.
- Isolation: `app/infrastructure/persistence/relationship_repository.py`,
  `person_query_port.py`, `app/api/v1/relationships.py`, `app/api/v1/persons.py`.
- Events: `app/infrastructure/event_dispatcher.py`,
  `app/infrastructure/unit_of_work.py`.
- Invitation: new domain/application/infrastructure/api slice + `clan_invitations`.
- Platform: `app/main.py`, `app/core/config.py`, `app/core/logging.py`,
  `app/core/rate_limit.py`, `app/core/database.py`, `app/services/scheduler.py`,
  `Dockerfile`, `docker-compose.yml`.
- Docs: `docs/architecture/bounded-contexts.md`, `docs/architecture/domain-rules.md`,
  `backend/CLAUDE.md`.
