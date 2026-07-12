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
- GET /me — viewer; supports `?include=stats` (adds a nested `stats` object)
- PATCH /me — admin
- GET /me/users — viewer; cursor-paginated (`cursor`, `limit` 1–100)
- GET /me/users/pending — admin; cursor-paginated
- POST /me/users/{user_id}/approve — admin
- POST /me/users/{user_id}/reject — admin
- PATCH /me/users/{user_id}/role — admin; `role` is a **query parameter**, not a body field
- DELETE /me/users/{user_id} — admin

Behavior:
- All operations are scoped by X-Current-Clan-Id.
- Admin-only operations mutate clan membership and role state.
- Paginated lists return the standard `{"data", "meta": {cursor, has_more, limit}}` envelope.
- Response shapes should remain consistent with user-facing admin workflows.

## Versioning & Compatibility Rules
- Adding new clan settings fields is non-breaking.
- Changing role semantics or approval flow is breaking.
- Keep membership and admin action envelopes stable for client handling.
