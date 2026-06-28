# Backend Design Review — Comprehensive Assessment (2026-06-28)

**Scope:** Every backend bounded context (auth, branch, clan, document, event, invitation, me,
person, platform_admin, relationship, tree), the cross-cutting concerns (clan isolation, RBAC,
Unit-of-Work + domain events, error envelope, config/boot/persistence), and the drift between the
code and the `docs/` tree (architecture, contracts, decisions, ops).

**Method:** A fan-out audit — one reviewer agent per unit reading the real code, followed by an
adversarial verifier per Critical/Important finding that tried to *refute* it against the source.
20 review units, 150 raw findings, every Critical/Important finding independently checked.

**How to read this:** Severities below are **post-verification** (a finding the verifier
down-graded is recorded at its corrected level; the 2 refuted findings are dropped). A finding
labelled *verified* survived an adversarial refutation attempt; *self-confirmed* was confirmed by
direct code reading during synthesis.

---

## 1. Executive summary

The backend is **architecturally strong and not yet production-ready**. The DDD/CQRS/hexagonal
skeleton is real and disciplined: the domain layer is genuinely framework-agnostic across all
contexts, ports are clean Protocols, the Unit-of-Work composes audit side-effects into the write
transaction, JWT validation is correct, and — most importantly — **clan-isolation on the read
path is consistently enforced and backed by real two-sided integration tests.** Several contexts
(relationship, clan, invitation) are textbook-clean.

The problems cluster into six themes, and they are the difference between "looks correct" and "is
correct":

| # | Theme | Why it matters | Worst severity |
|---|-------|----------------|----------------|
| A | **Schema is not self-contained** — three shipped endpoints reference DB objects no migration creates | `GET /me/clans`, the FCM-token endpoints, and the entire tree API **500 on a freshly-migrated database** | Critical ×3 |
| B | **Cross-clan *write* holes** — the read side is isolated, but create/update trust IDs from the request body | An editor in clan A can fabricate edges/persons over clan B's data, and reassign a person's controlling clan (privilege escalation over claim governance) | Critical ×2 |
| C | **Cross-clan *read* leaks in the tree** — the spouse fan-out and ancestor walk query global edge tables with no clan filter | Returns another clan's person PII (names, dates, photos) | Critical ×2 |
| D | **Clan suspension is a no-op** — `is_active=False` is never read on any request | The platform-admin "suspend a clan" capability does nothing; an abusive clan cannot be cut off | Critical ×1 |
| E | **The audit trail is silently incomplete** — three write paths forget `uow.track()`, and the claims path tracks a raw ORM model | No audit rows for event/branch/document writes; identity-claim submission **crashes at commit** | Critical ×1 |
| F | **The error envelope is broken on the auth surface** — auth/RBAC raise bare `HTTPException` | Every 401/403 returns FastAPI's default shape, bypassing the stable envelope and i18n | Critical ×1 |

**Verdict:** Do not run this against real clan data until Theme A (broken endpoints) and Theme B/C
(cross-clan access) are fixed. Themes D–F are required before it can be called auditable and
contract-stable. The foundations are good enough that all of this is fixable without
re-architecting — see the roadmap in §8.

---

## 2. Scorecard

**By post-verification severity:**

| Severity | Confirmed | Severity-adjusted | Unverified¹ | Refuted | Effective total |
|----------|-----------|-------------------|-------------|---------|-----------------|
| Critical | 10        | 0                 | 1 (now self-confirmed) | 0 | **11** |
| Important| 39        | 4                 | 7           | 2       | **~50** |
| Minor    | —         | 30 (down-graded)  | 57          | 0       | 87 |

¹ The `cross/auth-jwt-security` deep-dive unit and several `docs-decisions`/`docs-architecture`
verifiers did not complete (the org hit its monthly spend limit near the end of the run). Those
surfaces were nonetheless covered by adjacent units — JWT/JWKS correctness was *verified* under
`context/auth` and `cross/rbac-permissions`; the unverified ADR findings are corroborated by
first-hand knowledge (Redis/worker are deferred; the RLS pilot is intentionally inert at runtime).

**By unit** (C = effective Critical, I = effective Important after adjustment):

| Unit | C | I | Headline |
|------|---|---|----------|
| context/auth | 1 | 2 | Solid auth primitives; FCM table missing; registration bypasses UoW |
| context/branch | 0 | 2 | Clean; but never tracks events (no audit); update skips parent validation |
| context/clan | 0 | 1 | Strong isolation; promote-unapproved-to-admin gap; weak update validation |
| context/document | 1 | 3 | Clean + RLS pilot; no audit (no track); pagination over-returns; person_id unvalidated |
| context/event | 1 | 1 | Clean; **never tracks → no audit for any event write**; pagination leak |
| context/invitation | 0 | 1 | Best-guarded clan surface; accept/create races surface as 500 |
| context/me | 1 | 2 | **`GET /me/clans` selects a non-existent column**; zero tests |
| context/person | — | — | Thinly covered by its own unit; covered heavily by cross-cutting (see §4) |
| context/platform_admin | 1 | 2 | **Suspension is a no-op**; `clan_id` serialized as literal "None"; zero tests |
| context/relationship | 0 | 2 | Cleanest DDD slice; **cross-clan write hole**; soft-delete vs unique index |
| context/tree | 2 | 2 | **Missing SQL functions**; **spouse + ancestor leaks** |
| cross/clan-isolation | 1 | 3 | Read side solid; write-path cross-clan references unvalidated; empty `test_tenant.py` |
| cross/rbac-permissions | 1 | 2 | RBAC core sound; `created_by_clan_id` client-settable → escalation |
| cross/uow-events | 0 | 4 | UoW shape correct; `track()` is forgettable with no enforcement |
| cross/errors-envelope | 1 | 4 | Good backbone; auth raises bare `HTTPException`; ~37 missing i18n keys |
| cross/config-boot-persistence | 0 | 2 | Well-engineered; prod validator omits DSN/CORS; middleware order |
| docs/docs-architecture | 0 | 2+3? | New docs accurate; old docs claim RLS/Redis/worker that don't exist |
| docs/docs-contracts | 0 | 3 | Mostly accurate; branches+invitations undocumented; persons list-shape drift |
| docs/docs-decisions | 0 | (unverified) | ADR-004/005/008 accepted-but-deferred; ADR-007 claims path bypasses ADR-001 |
| docs/docs-ops | 0 | 2 | All five runbooks are empty scaffolds over real, non-trivial infra |

---

## 3. Critical findings (must fix)

### Theme A — Schema is not self-contained (broken on a clean DB)

**C1. FCM-token endpoints write to a table no migration creates** — *verified*
`backend/app/infrastructure/persistence/auth_repository.py:108-123`
`SqlAlchemyFCMTokenRepository.register_token/remove_token` run raw SQL against
`public.user_fcm_tokens(user_id, token, device_platform)`. No migration creates that table — the
only push-token table is `user_devices` (columns `fcm_token`, `platform`). So `POST/DELETE
/api/v1/auth/me/fcm-token` raise `UndefinedTable` → 500, and `notification.py:103` JOINs the same
missing table so anniversary push delivery is broken too. ORM model / raw SQL / migration are
three-way inconsistent. **Fix:** pick one source of truth — rewrite the repo onto `user_devices`
via the ORM, or add a migration creating `user_fcm_tokens` with an FK + `ON DELETE CASCADE` and
update `notification.py`. Add an FCM integration test (currently zero coverage).

**C2. `GET /api/v1/me/clans` selects a non-existent column `ucr.joined_at`** — *verified*
`backend/app/infrastructure/persistence/me_query_port.py:24,28`
`list_clans()` selects and `ORDER BY`s `ucr.joined_at`, but `user_clan_roles` has no such column
(neither ORM model nor migration). Every call raises `UndefinedColumn` → the primary endpoint of
the `me` context is non-functional, with no test to catch it. **Fix:** order by `ucr.created_at`
(low-risk) or add a real `joined_at` column + migration; add a test that executes `list_clans`
against the schema.

**C3. The tree read path depends on PostgreSQL functions no migration creates** — *verified*
`backend/app/services/tree_builder.py:86`, `backend/app/infrastructure/persistence/tree_repository.py:96`
`build_descendants_tree` calls `public.get_family_tree_flat(...)` and `find_path` calls
`public.find_relationship_path(...)`. Neither is defined in any Alembic migration (only
`f_unaccent` and `update_updated_at_column` exist). On a freshly-migrated DB every tree endpoint
(`/tree`, `/tree/subtree`, `/tree/path`) raises `UndefinedFunction` → 500. The clan-isolation of
`find_path` is delegated entirely to a function that does not exist, so it cannot even be reviewed.
The only tests mock the DB, hiding the gap. **Related Important** (`relationship`): cycle detection
calls `public.get_ancestors_flat`, which exists only in `infra/supabase/migrations/002_tree_functions.sql`,
**not** in the backend Alembic chain — the Alembic-managed schema is not self-contained. **Fix:**
add a migration that `CREATE OR REPLACE FUNCTION`s all three with the exact column contracts the
code reads, each filtering by `clan_id` + `is_deleted=false` with cycle protection; add an
integration test against a real Postgres.

### Theme B — Cross-clan write holes

**C4. Marriage / parent-child creation accepts arbitrary person UUIDs with no clan check** — *verified*
`app/application/relationship/handlers.py:39,92`, `app/domain/relationship/validator.py:38`
`MarriageCommandHandler.create` / `ParentChildCommandHandler.create` take `person1/2_id` (and
`parent/child_id`) straight from the body and persist an edge stamped `created_by_clan_id =`
caller's clan, but never verify those persons belong to the caller's clan. A clan-A editor can
create a marriage referencing clan-B persons. This is also the **precondition for the tree PII
leak** (C6): once the edge exists under clan A, clan A can read clan B's person names. The read
side is correctly isolated and tested — the hole is purely on create/update. **Fix:** before
constructing the entity, verify every referenced person is in `cmd.clan_id` (add
`persons_in_clan(ids, clan_id)` to the query port) and reject otherwise; add a cross-clan-rejection
integration test.

**C5. Editor/admin can reassign a person's controlling clan via `created_by_clan_id` on PATCH** — *verified*
`backend/app/schemas/person.py:89`, `backend/app/api/v1/persons.py:336`, `backend/app/domain/person/entity.py:115`
`PersonUpdateRequest` exposes a client-settable `created_by_clan_id`; the PATCH handler passes
`model_dump(exclude_unset=True)` into `Person.update`, which blindly `setattr`s every key, and
`created_by_clan_id` is in `UPDATABLE_FIELDS` so it is persisted. This is the field the **claim
authorization** path keys on (`ClaimCommandHandler._verify_admin_access` uses
`person.created_by_clan_id`), so rewriting it transfers claim-review control of a person to another
clan — a cross-clan integrity / privilege-escalation hole, not just data quality. The sibling
**Important** finding: the same field is client-settable on `POST /persons` create. **Fix:** remove
`created_by_clan_id` from `PersonCreateRequest`/`PersonUpdateRequest` entirely (it is provenance);
drop it from `UPDATABLE_FIELDS`; have `Person.update` reject keys outside an explicit editable
allowlist instead of `setattr`-ing arbitrary keys.

### Theme C — Cross-clan read leaks in the tree

**C6. Spouse fan-out query is not clan-scoped → leaks cross-clan person data** — *verified*
`backend/app/services/tree_builder.py:125-169`
The spouse query joins `marriages` → `persons` filtered only by `person id ∈ :ids AND is_deleted=false`,
with the `clan_memberships` join a decorative `LEFT JOIN`. For any node whose spouse edge was
created by another clan, the response returns that spouse's `full_name`, `gender`, `birth_date`,
`death_date`, `avatar_url`, `posthumous_name`. **Fix:** require the spouse person to have an
approved `clan_memberships` row for `:clan_id` (INNER JOIN / `WHERE EXISTS`), and/or filter
`marriages.created_by_clan_id = :clan_id`; add a non-member-spouse exclusion test.

**C7. `get_ancestors` recursive CTE walks `parent_child` globally with no clan filter** — *verified*
`backend/app/infrastructure/persistence/tree_repository.py:45-88`
The ancestors CTE joins `parent_child` only on `child_id = p.id AND is_deleted=false` — no
`created_by_clan_id = :clan_id` predicate. The only guard is a handler-side `person_in_clan` check
on the *starting* person; once recursion begins it returns every ancestor row regardless of clan.
**Fix:** add the clan predicate (or a required approved-membership check) to both the anchor and
recursive members of the CTE; add a boundary-stop integration test.

### Theme D — Suspension is a no-op

**C8. Clan suspension never blocks access anywhere** — *verified*
`backend/app/application/platform_admin/handlers.py:31`, `backend/app/core/security.py:140-199`
`suspend_clan` sets `clan.is_active=False`, but no part of auth, clan-resolution, or RBAC ever
reads `Clan.is_active` (grep confirms zero read-path usages). A suspended clan's members keep full
read **and write** access — the headline capability of `platform_admin` does nothing, and an
abusive clan cannot be cut off. **Fix:** in `get_current_clan_id` (or a dependency layered on it),
load the Clan and raise 403 (`clan_suspended`) when inactive, gating every clan-scoped route; add a
suspend-then-denied integration test. Consider modelling `active/suspended` as explicit aggregate
state with guarded transitions.

### Theme E — Audit trail silently incomplete

**C9. `EventCommandHandler` never tracks the aggregate → no audit log for any event write** — *verified*
`app/application/event/handlers.py:54,83,111`
`create/update/delete` call `save/delete` then `commit()` but never `uow.track(event)`. `commit()`
only collects events from tracked aggregates, so `EventCreated/Updated/Deleted` are dropped and
**no `AuditLog` row is ever written** for event mutations — breaking the auditability requirement.
Every other rich-aggregate handler tracks; event is the lone omission. (Branch and Document have
the **same Important-level** bug — see §4.) **Fix:** `self._uow.track(event)` before commit in all
three methods; add a handler test asserting an `AuditLog` row per operation.

**C10. Identity-claim submission tracks a raw ORM model → AttributeError at commit** — *self-confirmed*
`backend/app/application/person/claim_handlers.py:54,324`
`submit_claim` and `prelink_identity` call `uow.track(claim_model)` where `claim_model` is the
SQLAlchemy `IdentityClaim(TimestampMixin, Base)` — not an `AggregateRoot`, so it has no
`collect_events()`. `commit()` iterates `aggregate.collect_events()` → **AttributeError**. Both
paths have zero integration coverage (the one claim test exercises `approve`, which doesn't track),
so the crash is invisible to CI. **Fix:** make `IdentityClaim` a proper `AggregateRoot` (preferred,
aligns with ADR-001), or as a stop-gap remove the two `track(claim_model)` calls (the row is
already added + flushed and audit rows are added manually); add an integration test driving
`submit_claim` through `commit`.

### Theme F — Error envelope broken on the auth surface

**C11. Auth/RBAC paths raise raw `HTTPException`, bypassing the structured envelope and i18n** — *verified*
`backend/app/core/security.py:74,136,171,178,181,192`, `backend/app/core/permissions.py:57,62,65,103,108,111`
Token validation, clan-membership checks, role checks, and `X-Current-Clan-Id` parsing raise bare
`fastapi.HTTPException(detail="plain English")`. These are not `AppError` subclasses and `main.py`
registers no base-`HTTPException` handler, so every 401/403/400 from the auth layer returns
FastAPI's default `{"detail": ...}` instead of `{"error": {code, message, detail}}`, hard-coded in
English. This is the highest-traffic error class, so the "stable envelope" guarantee is broken
precisely on the auth surface; clients parsing `error.code` break on all auth failures. **Fix:**
replace the bare raises with the project error classes using stable codes (`invalid_token`,
`no_approved_membership`, `insufficient_permissions`, `clan_membership_required`,
`invalid_clan_id_format`, …), and/or register a `StarletteHTTPException` normaliser in `main.py`;
add the matching `error.<code>` i18n keys.

---

## 4. Important findings, grouped by theme

**Audit/UoW (the systemic version of C9):**
- **Branch** and **Document** write paths emit `AuditableEvent`s but never call `uow.track()` —
  same silent-drop as events (`branch/handlers.py:53,78,102`; `document/handlers.py:73,109,132`).
- **No enforcement that an aggregate with pending events was tracked** — the entire audit guarantee
  rests on every handler remembering `track()`, with zero feedback when forgotten
  (`unit_of_work.py:38-59`). **Recommended structural fix:** make tracking implicit at a seam that
  can't be forgotten — have `repository.save()/delete()/add()` call `uow.track()`, or use an
  `after_flush` hook. This single change retires the whole class (C9 + branch + document).
- **`set_avatar` is unaudited and takes no actor** (`document/handlers.py:112`) — a privileged
  person-facing state change leaves no trail.

**Layering violations (application imports infrastructure):**
- Seven handler modules type `uow` as the concrete `SqlAlchemyUnitOfWork` and/or import
  `supabase_client` directly (`clan`, `person`, `relationship`, `platform_admin`, `invitation`,
  `shared.audit`, `auth`). The fix is mechanical: depend on the domain `UnitOfWork` port; for auth,
  introduce an identity-provider port (`create_user/delete_user/sign_in/…`) with a Supabase adapter.
- **Auth registration/clan-create bypasses UoW + domain events entirely** — no aggregate, hand-rolled
  flush/commit (`auth/handlers.py:124-178`). Backed by strong DB invariants, but inconsistent with
  every other context and unaudited.

**Cross-clan write references (the Important siblings of C4/C5):**
- `POST /persons` trusts `body.created_by_clan_id` (`clan-isolation`, `rbac`).
- Event creation doesn't verify `person_id` is in the active clan (`event`, `clan-isolation`).
- Branch `update` can set a non-existent / cross-clan / cyclic `parent_branch_id` (create validates,
  update doesn't) (`branch/handlers.py:68`).

**Error envelope / i18n (the Important siblings of C11):**
- Pydantic `RequestValidationError` 422s return FastAPI's default `{detail:[…]}` shape (no handler).
- `me.select_clan` and `person.handlers:112` pass **human sentences / dynamic field lists as the
  error `code`** — non-stable, non-machine-readable, and unmatched by any i18n key.
- **~37 raised codes have no `error.<code>` i18n key**, so the translator returns the raw code as
  the user-facing message (`translator.py:32`). Includes base-class defaults (`not_found`,
  `validation_error`, …). Add a startup/test assertion that every raised code has a key.
- Registration echoes raw Supabase exception text into the client-visible detail (info leak).
- Domain `ValidationError` is missing from the status map → falls through to 400 instead of 422.

**Pagination:** Document and Event list endpoints return the `limit+1` sentinel row that
`paginate_query` fetches for `has_more` detection, and emit **no `next_cursor`** — over-returns one
row and breaks cursor pagination (`documents.py:50`, `events.py:48`, `pagination.py:42`).

**Validation gaps:** `ClanUpdateRequest` has no field constraints (blank name, unbounded
`founded_year`); clan `change_role` takes `role` as an untyped query param; `clan_invitations.role`
lacks the DB CHECK its sibling `user_clan_roles` has.

**Data-integrity edge cases:** soft-deleted relationship edges still occupy the unique index, so
re-creating a deleted edge fails with a raw 500 (add `WHERE is_deleted=false` to the indexes);
`platform_admin` audit serializer emits the literal string `"None"` for null `clan_id`;
`presigned_url_expires_at` is set to *now*, not now+TTL (clients see links as already expired).

**Boot/persistence:** the production fail-fast validator omits `DATABASE_URL` and `CORS_ORIGINS`
(a forgotten DSN boots silently against localhost); `RateLimitMiddleware` is outermost so 429s lack
CORS headers and bypass host validation (reorder: TrustedHost outermost, RateLimit innermost);
lifespan startup has no error isolation (one failing init aborts boot and skips teardown).

**Test gaps on sensitive surfaces:** `tests/test_tenant.py` — the file named for clan isolation —
is an empty `TODO` stub; `me` and `platform_admin` have **zero** test coverage (including the
super-admin auth gate); all tree tests mock the DB so no test exercises the real SQL or cross-clan
exclusion.

---

## 5. Per-context assessment (condensed)

- **auth** — Excellent isolation/RBAC primitives (`get_current_clan_id` defeats header spoofing;
  JWKS cache is correct and lock-guarded; registration compensation deletes orphaned Supabase users
  and is tested). Held back by C1 (FCM table), the UoW-bypass write path, and i18n gaps.
- **branch** — Clean hexagonal shape, correct read isolation and RBAC, safe `ON DELETE SET NULL`.
  Held back by the missing `track()` (no audit) and unvalidated `update` parent.
- **clan** — Strong: every membership mutation resolves the target via `(clan_id, user_id)` so
  cross-clan IDs return None; last-admin demotion guarded; good unit tests. Gaps: an admin can
  promote a still-**unapproved** member straight to admin; weak update-body validation.
- **document** — Clean aggregate + a genuinely good fail-closed RLS pilot with a real isolation
  test; strong DB CHECK/FK constraints. Gaps: no `track()` (no audit), pagination over-returns,
  `person_id` not clan-validated, racy single-avatar invariant.
- **event** — Clean and well-tested at the domain level; correct read isolation. The lone Critical
  is C9 (never tracks → no audit); plus the pagination leak and unvalidated `person_id`.
- **invitation** — The **best-guarded** clan surface: every admin route has RBAC + an explicit
  path-vs-active-clan guard with a dedicated negative test; 256-bit tokens; email-ownership check on
  accept; DB partial-unique index on pending. Gaps: accept/create races surface as 500 not 409.
- **me** — Architecturally clean read-only slice with correct `is_approved` filtering. Undermined by
  C2 (non-existent column) and zero tests.
- **person** — Its own review unit returned a thin result, **but the context is covered in depth by
  the cross-cutting units**: `created_by_clan_id` escalation (C5), create-path clan trust, the
  viewer self-edit carve-out (verified correct), and the read-isolation join (verified + tested).
- **platform_admin** — Correct super-admin gate (`platform_role=='super_admin' AND is_active`),
  good cursor pagination and audit actor capture. Undermined by C8 (suspension no-op), the `"None"`
  serialization bug, dict-typed responses (no Pydantic schemas), and zero tests.
- **relationship** — The **cleanest DDD slice**: pure domain, query-port validator, correct
  UoW/event flow, read isolation tested. The serious gap is C4 (cross-clan write) plus the
  soft-delete/unique-index collision and an update path that skips create-time invariants.
- **tree** — Clean read-only CQRS shape and good in-memory assembly tests, but two Criticals (C3
  missing functions, C6/C7 leaks) make it the highest-risk context.

---

## 6. Cross-cutting assessment

- **Clan isolation** — *Read side: strong and tested.* Every clan-scoped read filters by `clan_id`
  / `created_by_clan_id` / a `clan_memberships` join; `get_current_clan_id` resolves the active
  clan only from approved memberships (header spoofing defeated); there are real two-sided
  isolation tests. *Write side: the gap* — create/update across relationship, event, branch, and
  person trust IDs from the body (C4, C5, and their Important siblings). Plus the empty
  `test_tenant.py`.
- **RBAC** — Fundamentally sound: `viewer<editor<admin` correctly indexed, `is_approved=True`
  required everywhere, `platform_role` is a separate gate registration cannot self-grant, no
  privilege escalation in self-service flows. The one serious adjacent issue is C5
  (`created_by_clan_id` client-settable).
- **UoW + domain events** — Correct *shape* (flush → collect → dispatch in-transaction → commit; no
  direct `session.commit` in handlers; failing handler aborts the write). The weakness is that the
  guarantee depends on a forgettable `track()` call with no enforcement (C9 + branch/document).
- **Error envelope** — Good backbone (framework-agnostic hierarchy, adapter-layer mapping, verified
  no-traceback-leak 500 handler), but broken on the auth surface (C11) and undermined by missing
  i18n keys and code-misuse.
- **Config/boot/persistence** — Well-engineered for the stage: centralized psycopg-v3 DSN
  normalization (no driver drift), fail-fast prod validators, a correct session-level advisory-lock
  single-runner for the scheduler, and a hardened multi-stage Dockerfile with deploy-gated
  migrations. Only defensive gaps remain (validator coverage, middleware order, lifespan isolation).

---

## 7. Code ↔ docs drift matrix

| Doc | Claims | Reality | Severity |
|-----|--------|---------|----------|
| `architecture/multi-tenancy.md`, `data-model.md` | RLS actively enforces `clan_id` on every query; full RLS policies for persons/edges/events | RLS is a **single-table (`documents`) pilot, inert at runtime**; isolation is app-layer | Important |
| `architecture/overview.md` | A Redis event bus + a dedicated Worker service | Only `InMemoryEventDispatcher` exists; no worker | Important (unverified) |
| `architecture/api-design.md` | Platform endpoints gated by a `SUPER_ADMIN_UID` match; a clan-switch endpoint | Code uses the `platform_role` DB column; switch endpoint differs | Important→Minor |
| `architecture/rbac.md` | Deleting an event requires admin | Code requires only editor | Important (unverified) |
| `contracts/rest-me-api.md` | `POST /switch-clan` | Code implements `POST /clans/{clan_id}/select` | Important→Minor |
| `contracts/` (missing) | — | The **branches** and **invitations** routers are fully implemented but **undocumented** | Important |
| `contracts/rest-persons-api.md` | List returns `{data, next_cursor, has_more}` | Code returns `{data, total}` | Important |
| `contracts/rest-auth-api.md` | — | Implemented `POST /auth/onboard` is undocumented | Minor |
| `ops/*` (all five) | "What to document here" scaffolds | Real infra: Render preDeploy `alembic upgrade head` deploy-gate, psycopg-v3 unification, DSN-gated Sentry (0.1 prod sample), gitleaks/no-env CI gates — **none documented** | Important |
| `decisions/ADR-004` (Redis), `ADR-005` (export worker) | Accepted | **Zero implementation** (deferred) | Important (unverified) |
| `decisions/ADR-008` (RLS) | Accepted; lists runtime GUC injection, ContextVar seam, system DSN, startup BYPASSRLS assertion, CI coverage test | Only the pilot DDL landed; **runtime mechanism absent → RLS inert for the app** | Important (unverified) |
| `decisions/ADR-007` (claims) | Follows ADR-001 domain-event/UoW path | Claims path **bypasses** it and tracks a raw ORM model (C10) | Critical (per C10) |

**Accurate docs (no drift):** `architecture/bounded-contexts.md` and `domain-rules.md` (the newer,
Jun-28 docs) mirror the code precisely — isolation mechanisms, the parent-child validation
flowchart, exact error codes, the identity-claim state machine. `domain-events-catalog.md` matches
the event table and correctly marks the dispatcher in-process/non-durable. Most REST contracts
(clans, relationships, documents, platform-admin) match paths and methods exactly. `backend/CLAUDE.md`
is a faithful architecture summary.

---

## 8. Prioritized remediation roadmap

**Phase 0 — Make it run (blockers; the app 500s or crashes without these):**
1. C1 — fix the FCM-token table mismatch (+ test).
2. C2 — fix `me.list_clans` column (+ test).
3. C3 — add the three tree/cycle SQL functions to Alembic (+ integration test); fold in the
   `get_ancestors_flat` relocation so the Alembic schema is self-contained.
4. C10 — fix the claims `track(ORM model)` crash (+ `submit_claim`/`prelink` integration tests).

**Phase 1 — Close cross-clan access (security; do before any real clan data):**
5. C4 + siblings — validate every body-supplied person/clan reference belongs to the active clan on
   relationship/event/branch/person create & update (shared `persons_in_clan` check).
6. C5 — remove `created_by_clan_id` from person create/update DTOs + `UPDATABLE_FIELDS`; allowlist
   editable fields.
7. C6, C7 — clan-scope the tree spouse fan-out and ancestor CTE.
8. C8 — enforce `clan.is_active` in `get_current_clan_id`.
9. Implement `tests/test_tenant.py` as the end-to-end isolation gate (header spoof → 403; cross-clan
   create → rejected; per-clan role checks).

**Phase 2 — Auditability + contract stability:**
10. C9 + branch/document — fix the missing `track()`; **better**, make tracking implicit at the
    repository seam so the class can't recur.
11. C11 + envelope/i18n — normalise auth `HTTPException`s into the envelope, add a
    `RequestValidationError` handler, fix code-misuse, backfill the ~37 missing i18n keys + a
    coverage assertion.
12. Pagination — return proper `next_cursor`/`has_more` and stop leaking the sentinel row.

**Phase 3 — Docs sync (cheap, high-trust-impact):**
13. Correct `multi-tenancy.md`/`data-model.md` (RLS is a pilot, not active), `overview.md`
    (no Redis/worker), `api-design.md`/`rbac.md`; write `rest-invitations-api.md` and
    `rest-branches-api.md`; fix the persons list-shape contract; turn the five ops scaffolds into
    real runbooks (the facts already exist in code).
14. Reconcile the deferred ADRs (004/005/008) — mark "Accepted, deferred" with status + the
    activation work outstanding, so "Accepted" stops implying "implemented."

**Phase 4 — Hardening & layering:**
15. Migrate the seven handlers to the domain `UnitOfWork` port; add the auth identity-provider port.
16. Boot defenses: extend the prod validator (DSN/CORS), reorder middleware, isolate lifespan init.
17. Fill the `me` / `platform_admin` / `tree` test gaps; add the soft-delete-vs-unique-index fix.

---

## 9. What is genuinely strong (keep)

The domain layer's framework purity (verified zero FastAPI/SQLAlchemy/Pydantic imports across all
contexts); the read-side clan isolation and its two-sided integration tests; the RBAC core; the
UoW transaction shape; JWT/JWKS correctness; the relationship/clan/invitation contexts as DDD
exemplars; the psycopg-v3 DSN unification; the scheduler advisory-lock single-runner; the hardened
Dockerfile + deploy-gated migrations; and the fail-closed `documents` RLS pilot. These are the
foundation that makes the fixes above tractable rather than a rewrite.

---

## Appendix — Audit provenance & caveats

- Generated by a fan-out review workflow (20 units; one reviewer per unit + an adversarial verifier
  per Critical/Important finding). 150 raw findings; 49 confirmed, 34 severity-adjusted, 2 refuted.
- **Incomplete coverage** (org monthly spend limit reached near the end): the dedicated
  `cross/auth-jwt-security` deep-dive did not complete (covered by `auth` + `rbac`), and several
  `docs-decisions`/`docs-architecture` findings are *unverified* (marked inline; corroborated by
  first-hand repo knowledge). The two refuted findings ("login 500s with no profile"; "duplicate /
  age-gap validations are global not clan-scoped") were dropped.
- C10 was the one Critical whose automated verifier didn't run; it was **self-confirmed** by direct
  reading during synthesis.
