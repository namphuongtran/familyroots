# ADR-002: Single Schema Clan-Scoped Multitenancy

## Status
Accepted.

> **Update (2026-06-28):** The "Supabase RLS enforcement" in the Decision below is
> **deferred and NOT active**. Clan isolation is currently enforced in the
> **application/repository layer** — that is the primary, tested guarantee. RLS is a
> future defense-in-depth layer-2, and its approach has been superseded by
> [ADR-008](008-rls-defense-in-depth.md): app-GUC (`SET LOCAL app.clan_id`) policies
> rather than Supabase-native RLS, shipped as a `documents`-only pilot (`ENABLE`d,
> not `FORCE`d) while the app still connects as a bypass role. See ADR-008 and
> [multi-tenancy.md](../architecture/multi-tenancy.md).

## Context
The platform supports users who belong to multiple family clans.
The system needs strong tenant isolation without provisioning a separate database per clan.

## Decision
Use single-schema PostgreSQL with clan scoping:
- clan_id-based data partitioning in application models
- X-Current-Clan-Id request context selection
- Supabase RLS enforcement for defense in depth *(deferred — see Status note and [ADR-008](008-rls-defense-in-depth.md))*

## Consequences
Easier:
- operational simplicity versus per-tenant database strategy
- support for multi-clan users in one account
- centralized reporting and migrations

Harder:
- strict discipline required around tenant filters
- potential blast radius from query mistakes without robust guards/tests
