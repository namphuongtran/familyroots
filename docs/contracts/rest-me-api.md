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

## Versioning & Compatibility Rules
- Adding new membership metadata is non-breaking.
- Changing the clan-switch flow requires coordinated client updates.
- The selected clan context contract should remain explicit and stable.
