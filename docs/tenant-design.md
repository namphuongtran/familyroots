# Data Isolation Design

## Approach: Single Schema + clan_id + Row Level Security

FamilyRoots uses a single PostgreSQL schema with `clan_id`-based isolation,
enforced by Supabase Row Level Security (RLS).

## Why not separate schemas?

Separate-schema multi-tenancy was considered and rejected:

- **Over-engineered** for a genealogy platform — clans don't need infrastructure-level isolation from each other. They just need their own data to be private.
- **Breaks Supabase connection pooling** — PgBouncer and Supabase's built-in pooler don't work well with `SET search_path` switching per request.
- **Alembic becomes painful** — Running migrations across N schemas requires custom `env.py` logic, per-schema migration tracking, and slow sequential execution.
- **Infra complexity** — Tenant provisioner, per-tenant storage buckets, schema creation scripts — all unnecessary.
- **Supabase RLS is purpose-built for this** — Row Level Security policies enforce data isolation at the database engine level, which is as secure as separate schemas for this use case.

## Schema layout

```
PostgreSQL instance
└── public schema (all tables, data separated by clan_id column)
    ├── clans              (one row per clan)
    ├── members            (all clans' members, filtered by clan_id via RLS)
    ├── relationships      (filtered by clan_id via RLS)
    ├── documents          (filtered by clan_id via RLS)
    ├── events             (filtered by clan_id via RLS)
    ├── user_clan_roles    (which user belongs to which clan, with what role)
    └── platform_users     (super admin only — unchanged)
```

## How isolation works

1. Every clan-scoped table has `clan_id UUID NOT NULL` (via `ClanScopedMixin`).
2. RLS policies enforce `clan_id = auth.user_clan_id()` on every query.
3. Application layer also filters by `clan_id` explicitly (defense in depth) via the `get_current_clan_id()` FastAPI dependency.
4. Supabase Storage uses path-based isolation: `clans/{clan_id}/...` in a single shared bucket.
5. Backend always uses `get_current_clan_id()` dependency on protected routes.

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
- [Database Schema](database-schema.md) — table definitions
- [Architecture](architecture.md) — system overview
