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

> **Gap in this list, recorded 2026-08-22 by seed S-012 rather than backfilled.** Phases 6
> and 7 shipped on 2026-08-22 and have no bullet here: `clan_memberships` (migration
> `031_rls_clan_memberships`, seed S-009, proven by `test_rls_phase6_clan_memberships`) and
> `clan_invitations` (migration `032_rls_clan_invitations`,
> [ADR-048](048-invitation-accept-runs-on-the-system-session.md), seed S-043, proven by
> `test_rls_phase7_clan_invitations`). Both take the Phase-2 template on a NOT-NULL
> `clan_id`. S-012 did not write their entries, because it did not do that work and an ADR
> entry is a dated claim about what its author checked. The authority on the covered set is
> `test_rls_activation.py`, which enumerates it and fails on drift; this prose list is not.
> **The "Not yet" paragraph below is also stale in one clause as of that date:** it gives
> `clan_invitations` as excluded because of the unauthenticated accept-by-token path, and
> ADR-048 resolved exactly that by moving the accept route to the privileged session.

- **Phase 8 (2026-08-22, migration `033_rls_identity_claims`, seed S-012, decided by
  [ADR-042](042-identity-claims-app-layer-isolation-system-session-lockout.md))** — RLS
  enabled on `identity_claims` with **one deny-all policy**,
  `identity_claims_system_session_only FOR ALL USING (false) WITH CHECK (false)`.
  **This phase adds no clan isolation and must not be counted as coverage.** The table has
  no `clan_id` to compare (`app/models/identity_claim.py` reaches a clan only through
  `person_id` at `:32-36`), both claim handlers are wired on the privileged `get_system_db`
  by design (`app/infrastructure/dependencies.py:144`, `:149`), and two of the four claim
  routes resolve no clan at all. The policy is a **tripwire**: it converts a claims query
  mis-wired to `get_db` from a silent cross-clan read into zero rows and a rejected write.
  It catches a mis-wired *session*; it does not catch a missing *filter* on the correct
  session, and the application layer stays this table's only clan isolation. Proven by
  `test_rls_phase8_identity_claims` (denial under either clan and under none, with a
  privileged control proving the rows existed; INSERT rejected; UPDATE and DELETE touching
  no row; the system session still reading and writing; all four claim routes still working
  end to end with `get_db` on the real RLS session) and by
  `test_claim_cross_clan_pending_uniqueness` (the global one-pending-claim invariant, which
  a clan-keyed policy would have made uncheckable — ADR-042 § 5). The `ON DELETE CASCADE`
  from `persons` was measured under the policy and still fires. Because "RLS enabled with at
  least one policy" now answers yes for a table with no isolation, the coverage guard in
  `test_rls_activation.py` was split into `_CLAN_ISOLATED_TABLES` and
  `_REQUEST_ROLE_DENIED_TABLES`, and each half is asserted with its own question.

- **Phase 9 (2026-08-22, migration `034_rls_audit_notification`, seed S-014, decided by
  [ADR-043](043-audit-notification-rls-posture.md))** — RLS enabled on **two** tables with
  **two different shapes**, and the pair is the clearest statement of what decides membership
  of this layer: the reader, not the writer.
  - `notification_log` takes the Phase-2 template unchanged on a NOT-NULL `clan_id`. Its only
    accessors are the anniversary scheduler's dedup `SELECT` and `INSERT`
    (`app/services/scheduler.py:173`, `:201`), which run on a bare `engine.connect()` with no
    seam, so the policy is **inert today**. ADR-043 § 2 took that over a permanent exemption
    row in the coverage list. Proven by `test_scheduler_cross_clan_notification_log` (one job
    run writes for two clans while the policy is live) and by the two-sided DB-layer tests in
    `test_rls_phase9_audit_notification`.
  - `audit_logs` takes **per-command** policies: `audit_logs_sel` keyed on the GUC,
    `audit_logs_ins WITH CHECK (true)`, and **no `UPDATE` or `DELETE` policy**, which denies
    both commands to the request role and makes the trail append-only at the database. The
    permissive INSERT is forced by measurement, not preference: 13 of the 16
    `create_event_dispatcher` sites in `app/infrastructure/dependencies.py` hang off
    `Depends(get_db)`, and two of those routes — `POST /auth/register` (unauthenticated) and
    `POST /auth/onboard` — write an audit row with **no clan GUC at all**, so a clan-keyed
    `WITH CHECK` would compare `<real clan> = NULL` and reject registration. NULL-`clan_id`
    rows stay in the table, are invisible to every clan (`NULL = anything` is NULL), and are
    still returned in full by `GET /platform-admin/audit-log`, which runs on `get_system_db`
    and bypasses — so ADR-030 is untouched. ADR-043 explicitly rejects
    `USING (clan_id = GUC OR clan_id IS NULL)`. The ADR-038 `RETURNING` trap **was** live
    here and is fixed in the ORM in the same commit
    (`AuditLog.__mapper_args__ = {"eager_defaults": False}`), proven by
    `test_audit_write_paths_no_clan_guc` driving the two no-GUC routes over HTTP on a real
    `RlsSession`.
  - `audit_logs` fits neither half of the Phase-8 split, so `test_rls_activation.py` gained a
    third set, `_PER_COMMAND_TABLES`, with its own assertion: exactly a SELECT and an INSERT
    policy, the SELECT keyed on the GUC with no NULL branch, the INSERT permissive.
  - **This phase corrects one clause of the "Not yet" paragraph below**, which gives
    `audit_logs` as excluded for "nullable-clan platform rows + a super-admin cross-clan
    reader". Both facts are true and neither excludes the table: the nullable rows are the
    reason for a `SELECT`-only clan predicate, and the super-admin reader bypasses RLS
    entirely. The paragraph is left as the dated record of what was believed in 2026-06.

- **Phase 10 (2026-08-22, migration `035_rls_clan_settings`, seed S-010)** — `clan_settings`
  takes the Phase-2 template unchanged on a `clan_id` that is both NOT NULL and UNIQUE, one
  row per clan. It joins `_CLAN_ISOLATED_TABLES` because both halves of its single policy are
  clan-keyed. **S-010's other table, `user_clan_roles`, did not ship and could not**; see the
  amendment to the "Not yet" paragraph below.
  - Like `notification_log` in Phase 9, this policy is **inert on the day it ships**, and more
    completely so. Measured 2026-08-22 by `grep -rn 'clan_settings\|ClanSettings' backend/app`:
    the only application reference outside the ORM model is the `Clan.settings` relationship
    (`backend/app/models/clan.py:35`); nothing reads `clan.settings`, nothing constructs a
    `ClanSettings`, no route, repository or query port touches the table, and `001_initial.py`
    installs no trigger that would populate it. The table is empty and unread. ADR-043 § 2's
    reasoning applies unchanged: a cheap correct policy beats a permanent exemption row in
    S-015's list, because a second place to record a fact is a second place to be wrong.
  - **One live read path did have to be checked, and it is a trap worth naming.**
    `Clan.settings` is `lazy="selectin"`, so every load of a `Clan` ORM entity emits a second
    SELECT against `clan_settings`. Two such loads run on the RLS request session with **no
    clan GUC**: `get_clan_by_slug` and `get_clan_by_id`
    (`backend/app/infrastructure/persistence/auth_repository.py:47-49`, `:51-52`), both reached
    from `POST /auth/register` and `POST /auth/onboard`. Under the policy that selectin returns
    zero rows and `clan.settings` is `None`. Measured 2026-08-22: both onboard flows still
    answer `201`, because no caller consumes `clan.settings`. `Clan` declares five
    `lazy="selectin"` relationships (`clan.py:32-36`) and three of those targets — `persons`,
    `clan_memberships`, `branches` — have carried policies since Phases 4, 6 and 2, so the
    clan-less auth path has been loading a `Clan` with empty eager collections all along.
  - Because this table is empty in the running application, **"zero rows returned" is also its
    honest answer with no policy at all**. Every denial assertion in
    `backend/tests/integration/test_rls_phase10_clan_settings.py` therefore ends with a
    privileged read proving the rows were there — S-012's rule, at its sharpest here.

- **Phase 11 (2026-08-22, migration `036_rls_user_clan_roles`, seed S-052, decided by
  [ADR-050](050-user-clan-roles-clan-keyed-mutations.md))** — RLS enabled on `user_clan_roles`
  with **four per-command policies, two of which compare nothing**. `user_clan_roles_sel` is
  `USING (true)` and `user_clan_roles_ins` is `WITH CHECK (true)`; `user_clan_roles_upd` and
  `user_clan_roles_del` carry the Phase-2 predicate on every half they have. **This phase adds
  clan isolation to the write half only and must not be counted as full coverage.** The reason
  the read half is permissive is the census in ADR-050 § Context: four of the eleven modules that
  touch this table run on the request session with **no clan selected**, starting with
  `get_current_clan_id` itself (`app/core/security.py:249-254`, which sets the GUC only afterwards
  at `:290`), and a clan-keyed SELECT turns login into a silent lockout. The reason the write half
  is covered is sharper than for any table before it: `approve_if_pending`, `delete_role_by_id`,
  `delete_if_pending` and `change_role_if`
  (`app/infrastructure/persistence/clan_repository.py:136-155`, `:172-188`, `:190-205`,
  `:207-224`) are keyed on the primary key **alone**, with no `clan_id` predicate, so these two
  policies are the only thing at the database between a stray `ucr_id` and an admin grant in
  another clan. Proven by `test_rls_phase11_user_clan_roles` (UPDATE and DELETE denied across the
  boundary and admitted inside it, an UPDATE unable to move a row's `clan_id`, both commands
  denied with no clan selected, each denial closed by a privileged read proving the row was there
  and unchanged, and the permissive halves asserted so nobody closes one by accident) and by
  `test_rls_login_two_clans`, which drives login, `/me/clans` and both onboard branches over the
  real seam and adds the two-clan role check S-010 named. Because a fourth posture now exists, the
  coverage guard in `test_rls_activation.py` gained a fourth set,
  `_CLAN_KEYED_MUTATION_TABLES`, with its own question — listing this table as clan-isolated would
  have **passed** that set's assertion, because its UPDATE policy's `USING` does read the GUC.

> **Amendment (2026-08-22, Phase 11, seed S-052) — the `user_clan_roles` clause below, and the
> Phase-10 amendment above it, are now resolved by [ADR-050](050-user-clan-roles-clan-keyed-mutations.md).**
> The measurement stands: the migration-027 template does break the table in both directions, and
> both halves were reproduced again on 2026-08-22. What changed is the conclusion. The table is
> not excluded; it is **half covered**. `UPDATE` and `DELETE` are clan-keyed and `SELECT` and
> `INSERT` are permissive, so every clan-less reader and the clan-less `add_membership` write keep
> working on the session they were already on, and no handler moved. `clans` remains outside layer
> 2, so the clause below is still correct about that table.

> **Amendment (2026-08-22, Phase 10, seed S-010) — the `user_clan_roles` clause below is
> right, and it is now measured rather than predicted, in both directions.** It says RLS
> there "would default-deny and break every request". Re-measured on 2026-08-22 by adding
> `user_clan_roles` to migration 035's table list: it breaks two ways that look nothing
> alike, and the difference is the whole reason this is a decision rather than a patch.
> **The reads fail silently** — `get_current_clan_id` queries the table on the request
> session at `backend/app/core/security.py:249-254` and sets `app.clan_id` only afterwards
> at `:290`, and `get_login_profile` (`auth_repository.py:120-137`) and `list_clans`
> (`me_query_port.py:19-42`) read it before any clan exists to select, so `POST /auth/login`
> answers `200` with `clan_id: null` and `GET /me/clans` returns `[]`, with nothing raised
> and nothing logged. **The writes fail loudly** — `add_membership`
> (`auth_repository.py:69-88`) INSERTs the row on that same clan-less session, so both
> `POST /auth/onboard` flows raise `psycopg.errors.InsufficientPrivilege: new row violates
> row-level security policy for table "user_clan_roles"`, a 500. A policy that hides a role
> row does not merely hide data: it silently downgrades what the caller is allowed to do,
> because this is the table the authorization gate reads. The decision — move those reads to
> the privileged session, set the GUC earlier, or leave the table outside layer 2 — is owed
> its own ADR, pre-allocated as **ADR-050**. Pinned by
> `backend/tests/integration/test_rls_login_two_clans.py`, which covers both halves.

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

   > **Amended 2026-08-22 by [ADR-047](047-rls-seam-sets-clan-id-only.md), seed S-040 — read
   > this clause as `SET LOCAL app.clan_id = …` alone.** The `app.user_id` half was never
   > built and is not going to be. The shipped seam sets `SET LOCAL ROLE` plus `app.clan_id`
   > and nothing else (`backend/app/core/rls.py:63-65`), `get_current_clan_id` re-applies the
   > same single GUC mid-request (`backend/app/core/security.py:290`), and every policy in the
   > tree reads `app.clan_id` only: `grep -rho "current_setting('[^']*'"
   > backend/migrations/versions/*.py | sort | uniq -c` returned `6 current_setting('app.clan_id'`
   > and nothing else on 2026-08-22, while `grep -rn "app\.user_id" backend/ --include='*.py'`
   > returned nothing the same day. **The rest of § 2 stands unchanged**: app-specific GUCs
   > rather than Supabase-native `request.jwt.claims`/`auth.uid()`, and `SET LOCAL`'s
   > transaction scope, are both shipped and both still the reason for this clause. The
   > original sentence is left in place on purpose, because this file is a dated record of what
   > was decided in 2026-06 and ADR-047 § 2 explains why erasing it would be the worse defect.
   > ADR-047 also lists the five things a later seed must show before adding `app.user_id`.
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
- [ADR-047: The RLS Seam Sets `app.clan_id` Only](047-rls-seam-sets-clan-id-only.md) — amends
  Decision § 2 (2026-08-22, seed S-040); the `app.user_id` GUC was never built and is not added
- Backend production-hardening effort: application-layer isolation (SP-2B) is the
  primary mechanism; this RLS layer is SP-3C.
