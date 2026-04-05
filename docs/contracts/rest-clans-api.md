# Contract: clans-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/clans

Core operations:
- GET /me
- PATCH /me
- GET /me/users
- GET /me/users/pending
- POST /me/users/{user_id}/approve
- POST /me/users/{user_id}/reject
- PATCH /me/users/{user_id}/role
- DELETE /me/users/{user_id}

Behavior:
- All operations are scoped by X-Current-Clan-Id.
- Admin-only operations mutate clan membership and role state.
- Response shapes should remain consistent with user-facing admin workflows.

## Versioning & Compatibility Rules
- Adding new clan settings fields is non-breaking.
- Changing role semantics or approval flow is breaking.
- Keep membership and admin action envelopes stable for client handling.
