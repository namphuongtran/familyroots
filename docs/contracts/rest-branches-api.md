# Contract: branches-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/branches

Headers:
- Authorization: Bearer <jwt>
- X-Current-Clan-Id: <uuid>
- Accept-Language: vi|en|zh|fr

Core operations (role enforced per route; viewer < editor < admin):

| Method | Path            | Min role | Notes |
|--------|-----------------|----------|-------|
| GET    | `/branches`     | viewer   | List branches in the active clan, ordered by `branch_order` then name |
| POST   | `/branches`     | editor   | Create a branch (201) |
| GET    | `/branches/{id}`| viewer   | Branch detail (clan-scoped) |
| PATCH  | `/branches/{id}`| editor   | Update name/description/order/parent/founder |
| DELETE | `/branches/{id}`| admin    | Hard-delete (children + memberships `ON DELETE SET NULL`) |

Behavior:
- All reads/writes are scoped to the active clan (`get_current_clan_id`).
- Create and update validate body-supplied references against the active clan:
  `parent_branch_id` must be an existing branch in the clan (and not the branch
  itself), and `founder_person_id` must be a member of the clan — otherwise
  `branch_not_found` / `person_not_found` (404). (Direct self-parent is rejected;
  transitive cycles are a known, un-guarded limitation.)
- Branch create/update/delete emit auditable domain events → `audit_logs` rows.

Error envelope: standard `{ "error": { "code", "message", "detail" } }`.

## Versioning & Compatibility Rules
- Non-breaking: add optional fields, add optional query params.
- Breaking: remove/rename fields, change role requirements, change the error envelope.
