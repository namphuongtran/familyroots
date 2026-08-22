# Data Isolation Design

## Approach: Single Schema + clan_id, enforced in the application layer

FamilyRoots uses a single PostgreSQL schema with `clan_id`-based isolation.

> **Status (2026-08-02):** Isolation is enforced **in the application/repository
> layer** — this is the primary, tested guarantee. Row-Level Security is the
> **defense-in-depth layer-2** (ADR-008) and is **ACTIVE**: request traffic runs under
> the non-bypass `familyroots_app` role with a per-request `app.clan_id` GUC, so
> `documents`, `events`, `branches`, `parent_child`, `marriages`, `persons`,
> `change_requests`, `clan_memberships`, and `clan_invitations` are RLS-enforced at the DB
> layer (other clan-scoped tables are added table-by-table, and one of them cannot be — see
> point 7). A tenth table, `identity_claims`, has RLS **enabled with a deny-all policy that
> is not clan isolation** — see point 8, and do not read it as a covered table.
> `persons` carries two extra rules — see point 6 below and
> [ADR-038](../decisions/038-persons-returning-vs-membership-rls.md). The sections below
> describe the application-layer mechanism that remains the primary guarantee.

## Why not separate schemas?

Separate-schema multi-tenancy was considered and rejected:

- **Over-engineered** for a genealogy platform — clans don't need infrastructure-level isolation from each other. They just need their own data to be private.
- **Breaks Supabase connection pooling** — PgBouncer and Supabase's built-in pooler don't work well with `SET search_path` switching per request.
- **Alembic becomes painful** — Running migrations across N schemas requires custom `env.py` logic, per-schema migration tracking, and slow sequential execution.
- **Infra complexity** — Tenant provisioner, per-tenant storage buckets, schema creation scripts — all unnecessary.
- **RLS is purpose-built as layer 2** — Row Level Security enforces isolation at the database engine level as defense-in-depth behind the application layer (ADR-008), without the operational cost of separate schemas. This line said "a **future** layer-2 … (planned)" until 2026-08-22, four migrations after the first policy shipped, while the paragraph at the top of this file already listed seven covered tables. It is a reason to choose one schema, and the reason held; what went stale was the tense.

## Schema layout

```
PostgreSQL instance
└── public schema (all tables, data separated by clan_id / created_by_clan_id)
    ├── clans              (one row per clan)
    ├── persons            (global — created_by_clan_id is provenance only; visibility is
    │                       clan_memberships, in the app layer AND in RLS)
    ├── clan_memberships   (M:N link between persons and clans, filtered by clan_id;
    │                       RLS-enforced)
    ├── marriages          (global edges, write-gated by created_by_clan_id)
    ├── parent_child       (global edges, write-gated by created_by_clan_id)
    ├── documents          (filtered by clan_id in the app layer; RLS-enforced)
    ├── events             (filtered by clan_id in the app layer; RLS-enforced)
    ├── user_clan_roles    (which user belongs to which clan, with what role)
    ├── change_requests    (approval workflow queue, filtered by clan_id; RLS-enforced)
    └── audit_log          (cross-clan audit trail)
```

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
   `marriages`, `persons`, `change_requests`, `clan_memberships`, `clan_invitations`).** The request path drops to the non-bypass `familyroots_app`
   role and sets the transaction-local `app.clan_id` GUC (an `after_begin` seam on the
   request session, driven by a ContextVar `get_current_clan_id` sets), so those tables are
   RLS-enforced at the DB layer behind the primary application filters. System paths
   (scheduler/purge/migrations, plus the two cross-clan readers — identity claims and
   platform-admin metrics) use the privileged session and bypass. Remaining clan-scoped
   tables are added table-by-table. Gated by `RLS_ENABLED` (code-free rollback). See
   ADR-008.

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
   measured in that state on 2026-08-22 while closing S-009. **One is still open and one is
   now resolved**, and the resolved one shows the shape of the fix.

   - **`user_clan_roles`** is what `get_current_clan_id` reads to decide which clan is
     active (`backend/app/core/security.py:246-253`; the GUC is set only at `:290`), and
     what `get_login_profile` (`auth_repository.py:118-135`) and `GET /me/clans`
     (`me_query_port.py:19-42`) read. With a policy applied, `POST /auth/login` still
     answers `200` but with `clan_id: null`, and `/me/clans` returns `[]` — the user is
     told they belong to no clan. Pinned by
     `backend/tests/integration/test_rls_login_two_clans.py`.
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
   on, and that decision needs its own ADR. Seed S-009 enabled RLS on `clan_memberships` only
   for this reason; seed S-043 then made the decision for `clan_invitations`, and S-010 still
   owns `user_clan_roles`.

8. **`identity_claims` has RLS enabled and NO clan isolation, and the two facts are not in
   tension.** Migration `033_rls_identity_claims` (2026-08-22, seed S-012) creates exactly
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
