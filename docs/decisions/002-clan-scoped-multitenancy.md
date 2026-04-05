# ADR-002: Single Schema Clan-Scoped Multitenancy

## Status
Accepted

## Context
The platform supports users who belong to multiple family clans.
The system needs strong tenant isolation without provisioning a separate database per clan.

## Decision
Use single-schema PostgreSQL with clan scoping:
- clan_id-based data partitioning in application models
- X-Current-Clan-Id request context selection
- Supabase RLS enforcement for defense in depth

## Consequences
Easier:
- operational simplicity versus per-tenant database strategy
- support for multi-clan users in one account
- centralized reporting and migrations

Harder:
- strict discipline required around tenant filters
- potential blast radius from query mistakes without robust guards/tests
