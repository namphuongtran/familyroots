# Contract: platform-admin-api

## Type
REST API

## Owner
backend

## Consumers
- web
- ops/admin workflows

## Schema
Base route: /api/v1/platform

Core operations:
- GET /clans — cursor-paginated clan list (`{"data", "meta"}`)
- GET /clans/{clan_id}
- POST /clans/{clan_id}/suspend
- POST /clans/{clan_id}/reactivate
- GET /metrics — platform-wide counts (independent totals, not derived from page size)
- GET /audit-log — cursor-paginated; filters: `clan_id`, `action`, `cursor`, `limit`

Behavior:
- Every route is gated by the super-admin check (`user_profiles.platform_role`,
  resolved server-side — not a JWT claim and not clan-scoped).
- Used for platform-wide oversight rather than clan-scoped business workflows.
- Suspended clans reject clan-scoped requests with 403 `clan_suspended`.
- **`GET /audit-log` is newest-first (DESC)** — the single intentional exception to the
  otherwise-ASC list ordering, matching its "recent" purpose and its `created_at DESC`
  indexes (ADR-030). The opaque cursor still just walks the next (older) page.
  `audit_logs` is retained indefinitely (audit trail = compliance/heritage record; no
  retention purge by design — ADR-030).

## Versioning & Compatibility Rules
- Any change to super-admin authorization is high risk and should be treated as breaking.
- Keep platform-wide admin responses stable.
