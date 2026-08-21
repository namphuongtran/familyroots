# Data Isolation Design

## Approach: Single Schema + clan_id, enforced in the application layer

FamilyRoots uses a single PostgreSQL schema with `clan_id`-based isolation.

> **Status (2026-08-02):** Isolation is enforced **in the application/repository
> layer** — this is the primary, tested guarantee. Row-Level Security is the
> **defense-in-depth layer-2** (ADR-008) and is **ACTIVE**: request traffic runs under
> the non-bypass `familyroots_app` role with a per-request `app.clan_id` GUC, so
> `documents`, `events`, `branches`, `parent_child`, `marriages`, `persons`, and
> `change_requests` are RLS-enforced at the DB layer (other clan-scoped tables are added
> table-by-table).
> `persons` carries two extra rules — see point 6 below and
> [ADR-038](../decisions/038-persons-returning-vs-membership-rls.md). The sections below
> describe the application-layer mechanism that remains the primary guarantee.

## Why not separate schemas?

Separate-schema multi-tenancy was considered and rejected:

- **Over-engineered** for a genealogy platform — clans don't need infrastructure-level isolation from each other. They just need their own data to be private.
- **Breaks Supabase connection pooling** — PgBouncer and Supabase's built-in pooler don't work well with `SET search_path` switching per request.
- **Alembic becomes painful** — Running migrations across N schemas requires custom `env.py` logic, per-schema migration tracking, and slow sequential execution.
- **Infra complexity** — Tenant provisioner, per-tenant storage buckets, schema creation scripts — all unnecessary.
- **RLS is purpose-built as a future layer-2** — Row Level Security can enforce isolation at the database engine level as defense-in-depth behind the application layer (planned; ADR-008), without the operational cost of separate schemas.

## Schema layout

```
PostgreSQL instance
└── public schema (all tables, data separated by clan_id / created_by_clan_id)
    ├── clans              (one row per clan)
    ├── persons            (global — created_by_clan_id is provenance only; visibility is
    │                       clan_memberships, in the app layer AND in RLS)
    ├── clan_memberships   (M:N link between persons and clans, filtered by clan_id)
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
   `marriages`, `persons`, `change_requests`).** The request path drops to the non-bypass `familyroots_app`
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
