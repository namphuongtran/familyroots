# Contract: claims-api

## Type
REST API

## Owner
backend

## Consumers
- web
- backend admin workflows

## Schema
Base route: /api/v1/claims and /api/v1/clans/{clan_id}/claims

Core operations:
- `GET /claims` — list my claims (`cursor`, `limit`, `status` query params)
- `DELETE /claims/{claim_id}` — cancel a pending claim (204 No Content)
- `GET /clans/{clan_id}/claims` — list a clan's claims (`cursor`, `limit`, `status`, `fields`)
- `POST /clans/{clan_id}/claims/{claim_id}/approve`
- `POST /clans/{clan_id}/claims/{claim_id}/reject`
- `POST /clans/{clan_id}/claims/members/{user_id}/unlink` (204 No Content)
- `POST /clans/{clan_id}/claims/members/{user_id}/prelink` (201)

Behavior:
- Supports identity claim workflows for users and clan admins.
- Contains both user-facing and admin-facing surfaces.
- Both list endpoints are **cursor-paginated**: `cursor`/`limit` query params
  (default `limit=20`, max `100`). There is no `page`/`page_size` offset scheme.

Response shapes (see [Response envelope](README.md#response-envelope)):

`GET /claims` and `GET /clans/{clan_id}/claims`:
```json
{
  "data": [ { "id": "...", "user_id": "...", "person_id": "...", "status": "PENDING", "...": "..." } ],
  "meta": { "cursor": "opaque-string-or-null", "has_more": false, "limit": 20 }
}
```

`POST .../approve`, `POST .../reject`, `POST .../prelink` — single claim resource
under `data`:
```json
{ "data": { "id": "...", "user_id": "...", "person_id": "...", "status": "APPROVED", "...": "..." } }
```

`DELETE /claims/{claim_id}`, `POST .../unlink` — 204 No Content, no body.

## Versioning & Compatibility Rules
- Adding claim metadata is non-breaking.
- Changing approval state transitions is breaking.
- Keep review workflow contracts explicit and documented.
