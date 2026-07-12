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

### Last-admin invariant

A clan must always keep at least one approved admin. Both mutating endpoints below
enforce this under a `SELECT ... FOR UPDATE` lock on the clan's approved-admin rows
(`lock_admin_count`), so two concurrent requests that would both drop the clan to
zero admins serialize — exactly one succeeds, the other observes the post-commit
count and gets 403. The guard runs for **any** target, not just self-service:

- `PATCH /me/users/{user_id}/role` — demoting the clan's only approved admin away
  from `admin` (any target) → 403 `clan.last_admin_cannot_demote`.
- `DELETE /me/users/{user_id}` — removing the clan's only approved admin → 403
  `clan.last_admin_cannot_remove`. (Removing yourself is separately rejected with
  403 `clan.cannot_remove_self` regardless of admin count.)

See [error-codes.md](error-codes.md) for detail shapes and client handling.

## Versioning & Compatibility Rules
- Adding new clan settings fields is non-breaking.
- Changing role semantics or approval flow is breaking.
- Keep membership and admin action envelopes stable for client handling.
