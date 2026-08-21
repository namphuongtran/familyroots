# ADR-008: Row-Level Security as Defense-in-Depth Layer-2

## Status
Accepted — **Phase 1 ACTIVE: `documents` is RLS-enforced for application traffic**
(2026-07-25); table-by-table rollout in progress. The application layer remains the
PRIMARY isolation mechanism; RLS is defense-in-depth.

Shipped:
- Pilot (migration `002_rls_documents_pilot`, 2026-06-28) — the non-bypass
  `familyroots_app` role + the fail-closed `documents_clan_isolation` policy
  (`ENABLE`d, not `FORCE`d), proven at the DB level by `test_rls_documents`.
- **Phase-1 runtime activation (2026-07-25)** — the request path now drops to
  `familyroots_app` and sets the transaction-local `app.clan_id` GUC via an
  `after_begin` seam on a dedicated request session class (`app/core/rls.py`,
  `app/core/database.py::RlsSession`/`AsyncRequestSessionLocal`), driven by a request
  `ContextVar` that `get_current_clan_id` populates. Migration `026_rls_activation_grants`
  completes the role's grants (EXECUTE on functions, sequence usage). The
  `RLS_ENABLED`/`RLS_APP_ROLE` settings gate it (disabling is the code-free rollback).
  System paths (Alembic, scheduler, document-purge) use the default privileged session
  and legitimately bypass. Proven by `test_rls_activation` (seam applies role+GUC with
  no manual SET, re-applies after commit, fail-closed default-deny, system bypass,
  rollback switch, grant smoke, and a coverage-enumeration CI guard).

**Ordering blocker (resolved).** `get_current_clan_id → get_current_user → get_db`, so
the transaction begins before the clan is known. Resolution: the `after_begin` event
drops the role every transaction (auth deps touch only non-RLS tables in Phase 1), and
`get_current_clan_id` sets the GUC the moment it resolves the clan (plus records it in
the ContextVar so post-commit transactions re-apply it).

- **Phase 2 (2026-07-25, migration `027_rls_events_branches`)** — RLS extended to
  `events` and `branches` (same `clan_id = app.clan_id` policy). Both are read/written
  only by clan-scoped request handlers (GUC set); the anniversary scheduler reads
  `events` via the privileged system session (bypass). Proven by
  `test_rls_phase2_events_branches` (two-sided reads, WITH CHECK rejects a cross-clan
  write, fail-closed default-deny); the coverage guard now pins
  `{documents, events, branches}`.

- **Phase 3 (2026-07-25, migration `028_rls_edges`)** — RLS extended to the tree edges
  `parent_child` and `marriages` (policy on `created_by_clan_id`). The subtle risk vs
  events/branches: the SECURITY-INVOKER tree functions (`find_relationship_path`,
  `get_ancestors_flat`, the descendants CTE) and the `parent_child` BEFORE-ROW trigger run
  under the request role with the GUC set, so their edge queries become RLS-filtered —
  but they are already clan-scoped by `p_clan_id`/`created_by_clan_id` = the request's
  clan = the GUC, so the predicate is redundant and results are unchanged. No system path
  reads edges (only the scheduler reads `events`). Proven by `test_rls_phase3_edges`
  (two-sided reads, WITH CHECK cross-clan rejection, default-deny, **tree functions return
  correctly under the seam**, and **a write survives the BEFORE trigger + WITH CHECK**).
  Coverage guard now `{documents, events, branches, parent_child, marriages}`.

- **Phase 4 (2026-07-25, migration `029_rls_persons`)** — RLS extended to `persons`, the
  M:N table. Per-command policies keyed on `app.clan_id`: SELECT/UPDATE/DELETE require a
  `clan_memberships` membership of the active clan (read backstop); INSERT WITH CHECK
  `created_by_clan_id = GUC` (a membership-based WITH CHECK can't be used — `save_with_membership`
  inserts the person row before its membership row); UPDATE WITH CHECK permissive so
  soft-delete and shared-person edits (member here, origin another clan) don't break. The
  two **cross-clan** person readers — identity-claim handlers (a claimant resolves a person
  by global id, no membership yet) and platform-admin metrics (counts persons across all
  clans) — now run on the privileged **system session** (`get_system_db`), bypassing RLS;
  they write only non-RLS tables. Membership subquery is index-backed (perf-tested). The
  tree does not truncate because every edge-referenced person is a clan member. Proven by
  `test_rls_phase4_persons`. Coverage guard now `{documents, events, branches, parent_child,
  marriages, persons}`.

  - **Phase 4 follow-up (2026-08-02, ADR-038 — no migration).** The INSERT-ordering
    carve-out above was only half the problem. Postgres also matches a **`RETURNING`**
    row against the **SELECT** policy, so `INSERT INTO persons … RETURNING …` inside the
    same window is rejected by `persons_sel` even though `persons_ins` accepted the write
    — and SQLAlchemy 2.0's `eager_defaults="auto"` appends
    `RETURNING version, created_at, updated_at` to every `persons` INSERT. Every
    `POST /api/v1/persons` therefore failed under the non-bypass role; it was invisible
    until a test drove an HTTP write through a real `RlsSession`. Fixed in the ORM, not
    the policy: `Person.__mapper_args__ = {"eager_defaults": False}`. `029_rls_persons` is
    unchanged, the server defaults stay (the DB is still the timestamp/version authority),
    and no read plan changes. Widening `persons_sel` to
    `<membership> OR created_by_clan_id = GUC` — and the narrower "visible only while
    memberless" variant — were rejected because both let a clan keep reading a person
    after their `clan_memberships` row is removed; see ADR-038 for the empirical check.
    **Standing constraint:** any new `persons` write path must insert the membership row
    first or avoid `RETURNING`. Proven by `test_rls_person_create`.

- **Phase 5 (2026-08-22, migration `030_rls_change_requests`, seed S-008)** — RLS extended
  to `change_requests`. It takes the Phase-2 template unchanged: the column is a NOT-NULL
  `clan_id` (`app/models/change_request.py:19`), so the policy is
  `clan_id = <app.clan_id GUC>` on both USING and WITH CHECK. The table is read and written
  only by the two clan-scoped handlers wired on `get_db` (`get_change_request_command_handler`,
  `get_change_request_query_handler` in `app/infrastructure/dependencies.py`), so the GUC is
  always set and no system or unauthenticated path needs the bypass. The ADR-038 `RETURNING`
  trap does not bite here: one permissive ALL policy means the predicate that accepted the
  INSERT also admits the row it returns, which is checked rather than assumed. Proven by
  `test_rls_phase5_change_requests` (two-sided reads including a targeted read by id, INSERT
  and clan-reassigning UPDATE both rejected by WITH CHECK, a cross-clan review UPDATE
  touching no row, default-deny, and an ORM insert with RETURNING). Coverage guard now
  `{documents, events, branches, parent_child, marriages, persons, change_requests}`.

Not yet: RLS on the remaining clan-scoped tables. The **auth-flow / token / platform
tables are deliberately excluded for now** — `clans` and `user_clan_roles` are queried
by `get_current_clan_id` *before* it sets the GUC (RLS there would default-deny and break
every request until the GUC is moved earlier), `clan_invitations` is read by the
unauthenticated accept-by-token path, and `audit_logs` has nullable-clan platform rows +
a super-admin cross-clan reader. `change_requests` had none of those obstacles, which is
why it went first among the remainder (S-008). `persons`/`parent_child`/`marriages` need care (the M:N
`persons` policy is a `clan_memberships` subquery needing a perf check; the tree SQL
functions run SECURITY INVOKER under the role and would become RLS-filtered — verify they
still return correctly with the GUC set). A possible final `FORCE ROW LEVEL SECURITY`
comes once all tables are covered. Until each table is covered, its application-layer
filter remains its only enforced isolation.

## Context
Clan isolation is currently enforced entirely in the **application/repository
layer**: every clan-scoped read takes `clan_id` as a mandatory parameter and
filters on it (clan-owned tables by `clan_id`; relationship edges by
`created_by_clan_id`; persons by a `clan_memberships` join). This layer is
rigorous and covered by two-sided integration tests (a clan sees its own rows;
another clan gets not-found) across every read path.

We want a **second** line of defense at the database boundary so that a future
missed `WHERE clan_id = …` cannot leak cross-clan data. PostgreSQL Row-Level
Security (RLS) is the natural mechanism — but it is **inert** unless the
connecting role is non-superuser and lacks `BYPASSRLS`. Today the backend
connects as a bypassing role (local `postgres`; Supabase service-role), so
simply enabling RLS would be *false security*. Making RLS real therefore
requires a connection-model change and per-request context injection — the
highest-risk change in the production-hardening effort, because a mistake can
make every query return zero rows or error.

The mechanism, policy SQL, risks, and test plan are summarized in the Decision
section below; the shipped pilot lives in migration `002_rls_documents_pilot`
and `test_rls_documents`.

> 🇻🇳 **Tóm tắt:** Cô lập dòng họ hiện do **tầng ứng dụng** đảm bảo (mọi truy vấn
> clan-scoped đều lọc `clan_id`, đã test hai chiều). Ta thêm **lớp 2 ở tầng CSDL**
> bằng RLS để phòng trường hợp sau này lỡ quên một bộ lọc. Vướng mắc: backend đang
> kết nối bằng role **bypass RLS** (superuser/service-role) nên bật RLS suông là
> "bảo mật giả". Phải đổi cách kết nối + tiêm ngữ cảnh theo từng request — thay đổi
> rủi ro nhất, nên làm **pilot 1 bảng trước** rồi mở rộng.

## Decision
Adopt RLS as a **defense-in-depth second layer**; the application layer remains
the **primary** isolation mechanism and the source of truth. RLS must never be
the only thing standing between clans.

Implement it as follows (incrementally, pilot-first):

1. **Two connection contexts.** A dedicated non-privileged request role
   (`familyroots_app`, `NOBYPASSRLS`) for the FastAPI request path, under which
   RLS is enforced; and a separate privileged `SYSTEM_DATABASE_URL` for Alembic
   migrations and the cross-clan anniversary scheduler (which legitimately
   bypass RLS).
2. **App-specific GUC context, not Supabase-native.** Inject the active clan/user
   per transaction with `SET LOCAL app.clan_id = …` / `SET LOCAL app.user_id = …`
   and have policies read `current_setting('app.clan_id', true)`. This works
   identically on plain Postgres (local/CI) and Supabase, unlike
   `request.jwt.claims`/`auth.uid()` which require Supabase's `auth` schema.
   `SET LOCAL` is transaction-scoped, so it is pgbouncer-safe and cannot leak
   across pooled clients.
3. **Default-deny.** Policies treat an unset GUC as no access
   (`nullif(current_setting('app.clan_id', true), '')::uuid` → NULL → zero rows),
   so a code path that forgets to set context fails **closed**, never open.
4. **Context injection seam.** A request `ContextVar` (set after
   `get_current_clan_id`/`get_current_user`) drives `SET LOCAL` in the `get_db`
   session — keeping handler signatures unchanged.
5. **Policies mirror the app-layer rules.** Clan-owned tables by `clan_id`;
   edges by `created_by_clan_id`; `persons` via a `clan_memberships` membership
   subquery (M:N).
6. **Pilot-first rollout.** Ship RLS on **one** table (`documents`) plus the
   role, plumbing, and isolation tests as a self-contained first PR; expand
   table-by-table in subsequent, individually-reviewed phases. Each phase is an
   additive migration (role / `ENABLE RLS` / policies) that never touches
   baseline tables, so rollback is `DISABLE ROW LEVEL SECURITY` + drop policies
   (RLS off → the app layer still protects).

## Consequences
Easier:
- A database-level safety net that fails **closed**, catching a future missed
  application-layer filter before it leaks cross-clan data.
- Incremental, low-blast-radius rollout; trivial rollback (disable + drop).

Harder:
- Two connection contexts (request vs system) and the per-request GUC plumbing
  must be maintained; migrations/scheduler must use the system path.
- The `persons` M:N policy uses a per-row subquery — relies on the
  `clan_memberships(person_id, clan_id)` index and needs a performance check.
- New tables must be granted to the request role and given a policy; absence of
  either is a silent gap — guarded by a CI test enumerating RLS coverage.
- A startup/CI assertion is required to prove the request role does not bypass
  RLS (else the whole layer is silently inert).

## Related
- [ADR-002: Single Schema Clan-Scoped Multitenancy](002-clan-scoped-multitenancy.md)
- [ADR-038: `persons` RLS — Fix the RETURNING/`persons_sel` Collision in the ORM, Not in the Policy](038-persons-returning-vs-membership-rls.md) — amends Phase 4
- Backend production-hardening effort: application-layer isolation (SP-2B) is the
  primary mechanism; this RLS layer is SP-3C.
