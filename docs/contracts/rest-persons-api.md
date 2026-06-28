# Contract: persons-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/persons

Headers:
- Authorization: Bearer <jwt>
- X-Current-Clan-Id: <uuid>
- Accept-Language: vi|en|zh|fr

Core operations:
- GET /persons
  - Query params: cursor, limit, gender, alive, profile, fields, include
- POST /persons
- GET /persons/{id}
- PATCH /persons/{id}
- DELETE /persons/{id}
- POST /persons/{id}/restore
- GET /persons/{id}/timeline

Example response shape (list):
{
  "data": [...],
  "total": 123
}
- The persons list returns a `total` count (not a cursor envelope). `cursor`/`limit`
  query params drive which page of rows is fetched, but the response exposes `data`
  + `total`, not `next_cursor`/`has_more`.
- NOTE: `created_by_clan_id` is **not** accepted on create/update — it is provenance,
  always stamped from the active clan (see the 2026-06-28 design review, C5).

Example error shape:
{
  "error": {
    "code": "person_not_found",
    "message": "...",
    "detail": {
      "person_id": "..."
    }
  }
}

## Versioning & Compatibility Rules
- Non-breaking: add optional fields, add new include profile values, add new optional query params.
- Breaking: remove/rename fields, change required headers, change error envelope.
- Breaking changes require either:
  - additive compatibility period, or
  - new versioned route and migration notice in docs/decisions.
