# Data Isolation Design

## Approach: Single Schema + clan_id, enforced in the application layer

FamilyRoots uses a single PostgreSQL schema with `clan_id`-based isolation.

> **Status (2026-08-22):** Isolation is enforced **in the application/repository
> layer** — this is the primary, tested guarantee. Row-Level Security is the
> **defense-in-depth layer-2** (ADR-008) and is **ACTIVE**: request traffic runs under
> the non-bypass `familyroots_app` role with a per-request `app.clan_id` GUC, so
> `documents`, `events`, `branches`, `parent_child`, `marriages`, `persons`,
> `change_requests`, `clan_memberships`, `clan_invitations`, `notification_log`, and
> `clan_settings` are RLS-enforced at the DB layer. **The table-by-table rollout is
> finished.** Measured 2026-08-22: all **14** clan-owned tables now
> have row-level security enabled and a policy, and no clan-owned table is left outside
> layer 2. See the schema table above for the classification and point 10 for the gate that
> keeps it true. Fourteen tables have RLS enabled and **the number of fully covered tables
> is eleven**, because three of them carry policies that are not clan isolation, in three
> different ways: `identity_claims` is a deny-all tripwire (point 8), `audit_logs` is
> clan-keyed on reads only (point 9), and `user_clan_roles` is clan-keyed on `UPDATE` and
> `DELETE` only (point 7). `persons` carries two extra rules — see point 6 below
> and [ADR-038](../decisions/038-persons-returning-vs-membership-rls.md). The sections below
> describe the application-layer mechanism that remains the primary guarantee.

## Why not separate schemas?

Separate-schema multi-tenancy was considered and rejected:

- **Over-engineered** for a genealogy platform — clans don't need infrastructure-level isolation from each other. They just need their own data to be private.
- **Breaks Supabase connection pooling** — PgBouncer and Supabase's built-in pooler don't work well with `SET search_path` switching per request.
- **Alembic becomes painful** — Running migrations across N schemas requires custom `env.py` logic, per-schema migration tracking, and slow sequential execution.
- **Infra complexity** — Tenant provisioner, per-tenant storage buckets, schema creation scripts — all unnecessary.
- **RLS is purpose-built as layer 2** — Row Level Security enforces isolation at the database engine level as defense-in-depth behind the application layer (ADR-008), without the operational cost of separate schemas. This line said "a **future** layer-2 … (planned)" until 2026-08-22, four migrations after the first policy shipped, while the paragraph at the top of this file already listed seven covered tables. It is a reason to choose one schema, and the reason held; what went stale was the tense.

## Schema layout

One `public` schema holds every table. Data is separated by `clan_id` or
`created_by_clan_id` in the application layer, and by an RLS policy at the database for
every clan-owned table.

**This block used to be an eight-line sketch and it had gone stale in three ways**: it
named `audit_log` for a table called `audit_logs`, it omitted seven tables that exist, and
it gave no way to tell a clan-owned table from a platform-global one. The 2026-08-22 pass replaced
it with the full list, because the coverage gate in
`backend/tests/integration/test_rls_activation.py` now rests on exactly that distinction.
Measured 2026-08-22 against migration `036_rls_user_clan_roles`: `public` holds **18**
ordinary tables, **14** of them clan-owned, and all 14 carry a policy.

| Table | Clan-owned? | How the clan is reached | RLS posture |
|---|---|---|---|
| `persons` | yes | `created_by_clan_id` (provenance); visibility is `clan_memberships` | clan-isolated, per command |
| `clan_memberships` | yes | `clan_id` | clan-isolated |
| `branches` | yes | `clan_id` | clan-isolated |
| `documents` | yes | `clan_id` | clan-isolated |
| `events` | yes | `clan_id` | clan-isolated |
| `marriages` | yes | `created_by_clan_id` (global edge, write-gated) | clan-isolated |
| `parent_child` | yes | `created_by_clan_id` (global edge, write-gated) | clan-isolated |
| `change_requests` | yes | `clan_id` | clan-isolated |
| `clan_invitations` | yes | `clan_id` | clan-isolated (accept moved to the system session, ADR-048) |
| `clan_settings` | yes | `clan_id`, NOT NULL and UNIQUE | clan-isolated, inert today |
| `notification_log` | yes | `clan_id`, NOT NULL | clan-isolated, inert today |
| `identity_claims` | yes | no clan column at all; reaches one through `person_id` | deny-all tripwire (point 8, ADR-042) |
| `audit_logs` | yes | `clan_id`, nullable by decision | clan-keyed reads only (point 9, ADR-043) |
| `user_clan_roles` | yes | `clan_id` | clan-keyed `UPDATE`/`DELETE` only (point 7, ADR-050) |
| `clans` | **no** | it IS the tenant | outside layer 2 (ADR-008) |
| `user_profiles` | **no** | per-user identity; no owning clan | none |
| `user_fcm_tokens` | **no** | per-device push token, owned by a user | none |
| `alembic_version` | **no** | Alembic's own bookkeeping | none |

## How isolation works (application layer — the active mechanism)

1. **Read side.** Every clan-scoped read filters by clan explicitly:
   clan-owned tables (`documents`, `events`, `branches`) filter `clan_id`; relationship
   edges (`marriages`, `parent_child`) filter `created_by_clan_id`; `persons` are global
   and scoped via a `clan_memberships` join. There is intentionally **no tenant
   middleware** — scoping lives in the repositories.
2. **Active-clan resolution.** `get_current_clan_id()` reads the `X-Current-Clan-Id`
   header, validates the clan is in the caller's *approved* memberships (403 otherwise),
   and rejects a suspended clan (`is_active = false` → 403). Every clan-scoped route
   depends on it.
3. **Write side.** Create/update validate that body-supplied references (person ids on
   relationship/event/branch, founder/parent ids) belong to the acting clan, so a clan
   cannot attach its data to another clan's records. Relationship writes enforce this via
   `ensure_persons_in_clan` (a `clan_memberships` membership check → `404
   person_not_found`). Preventing **cross-clan edges** (an edge whose endpoint is not a
   member of the edge's clan, which the tree CTEs would otherwise traverse) is an
   accepted **application-layer** guarantee — there is intentionally no DB membership
   trigger; RLS layer-2 (below) is the planned database backstop. Pinned two-sided by
   `test_cross_clan_edge_guard.py`. See [ADR-031](../decisions/031-cross-clan-edges-app-layer.md).
4. **RBAC.** `require_role` / `RequireClanRole` re-derive the caller's role from
   `user_clan_roles` (filtered by `user_id` + `clan_id`, `is_approved = true`).
5. **Storage.** Path-based isolation: `clans/{clan_id}/...` in a single shared bucket.
6. **RLS layer-2 (ACTIVE for `documents`, `events`, `branches`, `parent_child`,
   `marriages`, `persons`, `change_requests`, `clan_memberships`, `clan_invitations`,
   `notification_log`, `clan_settings`; clan-keyed on reads only for `audit_logs`, see point 9;
   clan-keyed on `UPDATE` and `DELETE` only for `user_clan_roles`, see point 7).** The request path drops to the non-bypass `familyroots_app`
   role and sets the transaction-local `app.clan_id` GUC (an `after_begin` seam on the
   request session, driven by a ContextVar `get_current_clan_id` sets), so those tables are
   RLS-enforced at the DB layer behind the primary application filters. System paths
   (scheduler/purge/migrations, plus the two cross-clan readers — identity claims and
   platform-admin metrics) use the privileged session and bypass. **No clan-owned table is
   left to add**: Phase 11 (migration `036`) covered the last one, measured 2026-08-22 by
   the 2026-08-22 pass. Gated by `RLS_ENABLED` (code-free rollback). See ADR-008, whose own "Not yet"
   paragraph still reads as though tables remain — that paragraph is a dated record and this
   file is the current count.

   `persons` is the M:N exception: its policies are per-command and keyed on a
   `clan_memberships` membership subquery for SELECT/UPDATE/DELETE, with
   `WITH CHECK (created_by_clan_id = app.clan_id)` on INSERT because
   `save_with_membership` must write the `persons` row before its membership row. Two
   consequences follow, and both are load-bearing:

   - **`created_by_clan_id` is provenance, never visibility.** Removing a person's
     `clan_memberships` row makes them unreadable by that clan, including the clan that
     created them. Pinned by `test_rls_person_create.py::
     TestMembershipRemovalStillHidesThePerson`.
   - **No `RETURNING` on a `persons` INSERT before its membership row exists.** Postgres
     matches a `RETURNING` row against the SELECT policy, so the membership predicate
     would be evaluated in a window where it cannot hold. `Person` sets
     `eager_defaults=False` so SQLAlchemy never emits one; any new `persons` write path
     must insert the membership first or avoid `RETURNING`. See
     [ADR-038](../decisions/038-persons-returning-vs-membership-rls.md).

7. **A clan-scoped table cannot take a clan policy while any path reads it before a clan is
   chosen.** The request session drops to `familyroots_app` on every transaction, including
   such a path, so `app.clan_id` is empty, the predicate is NULL, and the table reads as
   empty. Nothing raises. The failure looks like a successful request with missing data —
   which is why this is written down rather than left to be rediscovered. Two tables were
   measured in that state on 2026-08-22. **One is still open and one is
   now resolved**, and the resolved one shows the shape of the fix.

   - **`user_clan_roles` had this shape and is now RESOLVED a third way**, by
     [ADR-050](../decisions/050-user-clan-roles-clan-keyed-mutations.md) and migration `036`.
     It is what `get_current_clan_id` reads to decide which clan is active
     (`backend/app/core/security.py:249-254`; the GUC is set only at `:290`), and what
     `get_login_profile` (`auth_repository.py:120-137`) and `GET /me/clans`
     (`me_query_port.py:19-42`) read. With the migration-027 template applied,
     `POST /auth/login` still answers `200` but with `clan_id: null`, and `/me/clans` returns
     `[]` — the user is told they belong to no clan. See the paragraph below for what shipped
     instead.
   - **`clan_invitations` had the same shape and is now RESOLVED**, by
     [ADR-048](../decisions/048-invitation-accept-runs-on-the-system-session.md) and
     migration `032`. `POST /invitations/{token}/accept`
     (`backend/app/api/v1/invitations.py:95`) deliberately has no `get_current_clan_id` —
     the invitee is not a member yet — and `get_by_token`
     (`invitation_repository.py:53`) has no `clan_id` predicate, because the token is the
     authorization. So that ONE route moved to its own provider on the privileged system
     session (`get_invitation_accept_handler`, `dependencies.py:358-362`), while create,
     list and revoke stayed on `get_db` and are what the policy protects. The accept path
     therefore keeps one layer of clan isolation where the other three have two, which
     ADR-048 records rather than hides. Pinned by
     `backend/tests/unit/api/test_invitation_accept_session_wiring.py` (the route resolves
     the right session) and
     `backend/tests/integration/test_invitation_accept_no_clan_context.py` (the session
     choice still produces the right behaviour against the real policy).

   Covering a table in this shape means first deciding which session its clan-less path runs
   on, and that decision needs its own ADR. Phase 6 enabled RLS on `clan_memberships` only
   for this reason; ADR-048 then made the decision for `clan_invitations`; Phase 10 split
   the same way, shipping `clan_settings` (migration `035`); and ADR-050 closed the last of
   them for `user_clan_roles` (migration `036`). **There are now three answers to this shape,
   not one:** move the one clan-less route to the privileged session (ADR-048), lock the table
   out of the request role entirely (ADR-042), or cover only the commands whose paths all have
   a clan (ADR-050). Which one fits depends on how many clan-less paths there are and what they
   do.

   **`user_clan_roles` is the sharpest instance of this shape, because it is the table the
   authorization gate reads.** A policy there does not merely hide data: it silently
   downgrades what the caller may do. Re-measured 2026-08-22, and it breaks in two
   unlike ways. **Silently on reads:** `get_current_clan_id` queries the table on the request
   session (`backend/app/core/security.py:249-254`) and sets `app.clan_id` only afterwards at
   `:290`; `get_login_profile`
   (`backend/app/infrastructure/persistence/auth_repository.py:120-137`) and `list_clans`
   (`backend/app/infrastructure/persistence/me_query_port.py:19-42`) run before any clan
   exists to select. `POST /auth/login` answers `200` with `clan_id: null` and
   `GET /me/clans` returns `[]`, with no error anywhere. **Loudly on writes:**
   `add_membership` (`auth_repository.py:69-88`) INSERTs the row on that same session, so both
   `POST /auth/onboard` flows raise `InsufficientPrivilege` and answer 500. Both halves are
   pinned by `backend/tests/integration/test_rls_login_two_clans.py`.

   **[ADR-050](../decisions/050-user-clan-roles-clan-keyed-mutations.md) resolved it by covering
   half the table, and the half it chose is the opposite of `audit_logs`'s.** Migration `036`
   gives `user_clan_roles` four per-command policies: `SELECT USING (true)` and
   `INSERT WITH CHECK (true)`, both permissive by decision, and clan-keyed `UPDATE` and
   `DELETE`. The reason is that a **record** leaks by being read while a **capability** leaks by
   being written. Measured 2026-08-22: the four statements that mutate this table on a request
   session — `approve_if_pending`, `delete_role_by_id`, `delete_if_pending` and `change_role_if`
   (`backend/app/infrastructure/persistence/clan_repository.py:136-155`, `:172-188`, `:190-205`,
   `:207-224`) — are keyed on the **primary key alone**, with no `clan_id` predicate. Their clan
   safety today is that `ucr_id` came from the clan-filtered `get_user_clan_role` (`:31-39`) a
   few lines earlier, which is a read-then-write pair rather than a filter. So the reads on this
   table have one layer of isolation and the authority-changing writes now have two. No handler
   changed the session it runs on. Proven both ways at the database layer by
   `backend/tests/integration/test_rls_phase11_user_clan_roles.py`.

8. **`identity_claims` has RLS enabled and NO clan isolation, and the two facts are not in
 tension.** Migration `033_rls_identity_claims` (2026-08-22) creates exactly
   one policy, `identity_claims_system_session_only FOR ALL USING (false) WITH CHECK (false)`.
   It compares nothing to `app.clan_id`. The request role is locked out of the table whatever
   clan is selected, and the application layer is this table's **only** clan isolation.
   [ADR-042](../decisions/042-identity-claims-app-layer-isolation-system-session-lockout.md)
   made that choice and refuses to call the policy a second layer.

   Three facts forced it, and each is bigger than the missing column. The table has no
   `clan_id`: it reaches a clan only through `person_id`, and the clan it reaches is the
   person's **nullable origin** (`persons.created_by_clan_id`, `ON DELETE SET NULL` per
   ADR-009), which is provenance rather than membership. Both claim handlers are wired on
   the privileged `get_system_db` on purpose — a claimant resolves a person by global id and
   is not yet a member of that person's clan — so any predicate added today would be inert.
   And `POST /persons/{person_id}/claim` runs under the **claimant's** active clan, not the
   claimed person's, so a clan-keyed policy would reject the one insert the feature exists to
   perform.

   **What the policy is for.** It is a tripwire for a mis-wired session: a claims query
   pointed at `get_db` returns zero rows and a rejected write in the author's own test run,
   instead of quietly reading every clan's claims. It does **not** catch a missing
   `created_by_clan_id` filter on the correct session. If a future read path forgets that
   filter, one clan's admin sees another clan's claims — the claimant's user id, the person
   id, and both note fields. That residual risk is accepted in ADR-042 and mitigated by
   nothing else.

   **The consequence for any coverage check.** "RLS enabled with at least one policy" answers
   yes for this table and means nothing by it. The guard in
   `backend/tests/integration/test_rls_activation.py` is therefore split into
   `_CLAN_ISOLATED_TABLES` and `_REQUEST_ROLE_DENIED_TABLES`, and each half is asserted with
   its own question: a clan-isolated table must have a policy whose `USING` clause reads
   `app.clan_id`, and a denied table must have every policy reading `USING (false)` and
   `WITH CHECK (false)`. Pinned by `test_rls_phase8_identity_claims.py` and
   `test_claim_cross_clan_pending_uniqueness.py`.

9. **`audit_logs` is clan-keyed on reads, wide open on writes, and closed to edits — three
   different answers on one table.** Migration `034_rls_audit_notification` (2026-08-22, seed
   ADR-043) implements
   [ADR-043](../decisions/043-audit-notification-rls-posture.md) and creates two policies and
   deliberately no third:

   | Command | Policy | Effect on `familyroots_app` |
   |---|---|---|
   | `SELECT` | `audit_logs_sel USING (clan_id = <app.clan_id GUC>)` | reads its own clan only |
   | `INSERT` | `audit_logs_ins WITH CHECK (true)` | may write a row naming any clan, or none |
   | `UPDATE` | none | denied — no matching policy |
   | `DELETE` | none | denied — no matching policy |

   **The permissive INSERT is the decision, not the oversight.** Most audit rows are written
   by the request role: `AuditLogHandler` is wired by `create_event_dispatcher(db)`, and 13
   of its 16 sites in `backend/app/infrastructure/dependencies.py` hang off `Depends(get_db)`.
   Two of those routes have no clan GUC at all — `POST /api/v1/auth/register`, which is
   unauthenticated, and `POST /api/v1/auth/onboard` — so a clan-keyed `WITH CHECK` would
   compare `<real clan> = NULL` and reject registration outright.

   **NULL-`clan_id` rows are retained, invisible to every clan, and fully visible to the
   platform surface.** `clan_id` is nullable on purpose (`backend/app/models/audit_log.py:18-21`):
   platform-level actions have no clan, and ADR-009's `ON DELETE SET NULL` means deleting a
   clan does not erase its trail. `NULL = <anything>` is NULL in SQL, so `audit_logs_sel`
   hides those rows from every clan with no special case. ADR-030's super-admin surface is
   untouched because `get_audit_log` runs on `get_system_db`, which never issues
   `SET LOCAL ROLE`. **Do not "fix" this with `USING (clan_id = GUC OR clan_id IS NULL)`** —
   ADR-043 names that as the predicate a reader reaches for and rejects it, because it
   publishes every platform action to every clan.

   **The absent UPDATE/DELETE policies make the trail append-only at the database.** Under
   RLS a command with no matching policy is denied for a non-bypass role. `audit_logs` was
   already documented as an "immutable log of all write actions"; this is the first thing
   that enforces it.

   **Consequences for a coverage check, on top of point 8's.** `audit_logs` fits neither
   `_CLAN_ISOLATED_TABLES` nor `_REQUEST_ROLE_DENIED_TABLES`, so
   `backend/tests/integration/test_rls_activation.py` carries a third set,
   `_PER_COMMAND_TABLES`, asserted by its own test: exactly a SELECT and an INSERT policy,
   the SELECT keyed on the GUC with no NULL branch, the INSERT permissive. Pinned two-sided
   at the DB layer by `test_rls_phase9_audit_notification.py`, and at the HTTP layer by
   `test_audit_write_paths_no_clan_guc.py`, which drives the two no-GUC writers through a
   real `RlsSession`. `notification_log` took the ordinary template in the same migration and
   needs none of this; its only accessor is the anniversary scheduler, which bypasses, and
   `test_scheduler_cross_clan_notification_log.py` proves that run still crosses clans.

 **A fourth set followed on the same day (2026-08-22,
   [ADR-050](../decisions/050-user-clan-roles-clan-keyed-mutations.md)).** `user_clan_roles`
   fits none of the three above: its `SELECT` and `INSERT` are `true` and its `UPDATE` and
   `DELETE` are clan-keyed, which is the mirror of `audit_logs`. `_CLAN_KEYED_MUTATION_TABLES`
   is asserted by its own test — exactly one policy per command, the mutating pair keyed on the
   GUC on every half they have, the reading pair required to stay `true` so nobody tightens one
   without moving the clan-less readers first. **Listing it as clan-isolated would have passed
   that set's assertion**, because its `UPDATE` policy's `USING` does read the GUC. Three seeds
   in a row have now found a guard passing over the wrong thing; the rule is
 `.claude/rules/testing.md` § "A test pins an outcome, not a setting", and its last line — a set
   is a setting too — is why a fourth set exists instead of a fourth name in an old one.

10. **The four sets say what each listed table's policies do. Nothing said which tables they
    are obliged to cover, and that silence was closed on 2026-08-22.** Each of
    the four assertions iterates its own members, so a clan-owned table in **none** of them
    was a table no question was ever asked about. A new table could ship with no policy at
    all and the whole suite stayed green. This is not a hypothetical: eight tables went
    uncovered across migrations `027`, `028` and `029`, found on 2026-08-13 by listing
    `__tablename__` and grepping the migrations by hand.

    **The rule: every ordinary table in `public` is clan-owned unless it is named in
    `_NOT_CLAN_OWNED_TABLES`, with its reason, in
    `backend/tests/integration/test_rls_activation.py`.** The universe comes from `pg_class`
    rather than from a written list, so a table added by a migration is inside the gate the
    moment the migration runs. The default is deliberately the strict one: the failure this
    repository has actually suffered is a table shipping **unclassified**, so defaulting to
    "global" would reproduce exactly that silence, while defaulting to "clan-owned" turns an
    omission into a named failure on the day it lands.

    **"It has a `clan_id` column" is not the membership rule, and this file holds one
    counter-example in each direction.** `identity_claims` has no clan column at all and is
    in scope (point 8). `audit_logs.clan_id` is nullable on purpose, so the column's presence
    says nothing about whether every row has an owning clan (point 9). The column signal is
    used for the one job it is sufficient for instead: a **veto**. A table with a foreign key
    to `clans`, or a column whose name ends in `clan_id`, may never be named as not
    clan-owned. That is what stops an exemption being added quietly to make a red gate go
    green — the one edit that would otherwise defeat the whole check.

    **Four tables are named as not clan-owned, and two of them rest on no ADR.** `clans` is
    the tenant registry itself, kept outside layer 2 by ADR-008. `alembic_version` belongs to
    Alembic. `user_profiles` and `user_fcm_tokens` are per-user identity: a profile exists
    before any clan and may belong to several, so no single clan owns the row.
    **No ADR decides that last pair.** ADR-048 and ADR-050 each state as a fact that
    `user_profiles` carries no policy; neither decides that it should not. The 2026-08-22 pass recorded
    that as owed rather than citing an ADR that does not say it.

    The gate is `test_every_clan_owned_table_is_covered_by_exactly_one_of_the_four_postures`,
    and it fails on four shapes: a clan-owned table in no set, a set naming a table that is
    not clan-owned, a table in two sets, and a clan-owned table with RLS disabled or enabled
    with no policy. **RLS-disabled is the shape the older guard could not see at all** — it
    enumerated `relrowsecurity` tables, so a table that never had row-level security switched
    on was invisible to it, which is why a drop-the-policy control never reached it. The
    exemption list has its own guard,
    `test_the_not_clan_owned_list_names_only_tables_the_schema_agrees_are_global`. Every one
    of those shapes was planted and watched failing on 2026-08-22.

## Multi-clan membership (clan switcher)

Users can belong to multiple clans (e.g., a genealogist managing several family trees). The clan switcher works like Slack's workspace switcher:

### Flow

1. **Login** — `GET /api/v1/me/clans` returns all clans the user belongs to.
2. **Single clan** — if only one membership, auto-selected (no UI needed).
3. **Multiple clans** — client shows a clan selector UI.
4. **Selection** — `POST /api/v1/me/clans/{clan_id}/select` validates membership and returns clan details.
5. **Persistence** — client stores selected `clan_id` in local storage.
6. **Subsequent requests** — client sends `X-Current-Clan-Id: <uuid>` header on all clan-scoped API calls.

### Backend implementation

- `get_current_clan_id()` FastAPI dependency reads the `X-Current-Clan-Id` header.
- If 1 clan + no header → auto-selects (zero-friction for single-clan users).
- If multiple clans + no header → returns `400` with instructions.
- If header is sent but user isn't a member → returns `403`.
- Stateless design — no server-side session required.

## Onboarding a new clan

Creating a new clan is simply:
1. `INSERT` into `public.clans` (via super admin or self-registration flow)
2. `INSERT` into `public.user_clan_roles` for the founding admin
3. No schema creation. No migrations. No storage bucket setup.

Done in under 100ms.

## Related

- [RBAC](rbac.md) — role hierarchy within clans
- [Data Model](data-model.md) — table definitions
- [Overview](overview.md) — system overview
- [ADR-008](../decisions/008-rls-defense-in-depth.md) — RLS defense-in-depth (layer-2, active)
- [ADR-038](../decisions/038-persons-returning-vs-membership-rls.md) — the two extra rules `persons`-RLS imposes (provenance ≠ visibility; no `RETURNING` before the membership row)
