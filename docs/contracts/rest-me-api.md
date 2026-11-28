# Contract: me-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/me

Core operations:
- GET /clans — list the current user's approved clan memberships
- POST /clans/{clan_id}/select — validate membership and select the active clan
- DELETE / (that is, `DELETE /api/v1/me`) — delete the caller's own account (ADR-079)

Behavior:
- `GET /clans` returns the user's **approved** memberships only (pending/unapproved are excluded).
- `POST /clans/{clan_id}/select` validates the user has an approved membership in that clan
  (403 `clan_membership_required` otherwise) and echoes the selected clan context.
- Clients must persist the chosen clan context and send `X-Current-Clan-Id` on subsequent
  clan-scoped requests; `get_current_clan_id` re-validates membership (and clan `is_active`)
  on every such request.

Response shapes (see [Response envelope](README.md#response-envelope)):

`GET /clans` — a plain canonical array under `data`, no `meta` (all approved
memberships; a clan switcher is not paginated). Use `data.length` for the count:
```json
{
  "data": [
    { "clan_id": "...", "clan_name": "...", "clan_slug": "...", "role": "...", "joined_at": "..." }
  ]
}
```

`POST /clans/{clan_id}/select`:
```json
{
  "data": {
    "clan_id": "...", "clan_name": "...", "clan_slug": "...", "role": "...",
    "message": "Clan selected. Set X-Current-Clan-Id header to this clan_id on subsequent requests."
  }
}
```

`DELETE /api/v1/me` — 200 with a message envelope:
```json
{ "data": { "message": "Your account has been deleted." } }
```
- Removes the caller's identity-provider account, every clan role and membership
  (`user_clan_roles`, approved or pending, in every clan), their identity claims and push
  tokens, and the personal data of their profile (email, display name, avatar, person
  link). The profile row stays as a deactivated tombstone, so the caller's still-valid
  access token now answers 403 `account_deactivated` on every other route.
- **403 `account.last_admin_transfer_first`** while the caller is the only approved admin
  of a clan; `error.detail.clan_ids` lists those clans. Nothing is changed. Promote
  another member to admin (`PATCH /clans/me/users/{user_id}/role`) first.
- **503** when the identity provider is unavailable. The database part is already done;
  sending the same request again completes the deletion (it accepts the caller's token
  even though the account is now deactivated).
- The family-tree person the account was linked to is **not** removed. It is clan data,
  and a clan admin can anonymise it (`POST /persons/{id}/anonymise`).
- Audited as `account.delete`: one row per clan left (with that `clan_id`) and one
  platform row (`clan_id` null).

## Versioning & Compatibility Rules
- Adding new membership metadata is non-breaking.
- Changing the clan-switch flow requires coordinated client updates.
- The selected clan context contract should remain explicit and stable.
