# Contract: relationships-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/relationships

Marriage endpoints:
- POST /marriages
- GET /marriages/{id}
- PATCH /marriages/{id}
- DELETE /marriages/{id}

Parent-child endpoints:
- POST /parent-child
- GET /parent-child/{id}
- PATCH /parent-child/{id}
- DELETE /parent-child/{id}

Validation rules (current behavior):
- prevent self-loops
- prevent duplicate active marriage relationships
- max biological parent constraints
- age-gap and cycle checks for parent-child edges

Response shapes (see [Response envelope](README.md#response-envelope)):
- All endpoints return the resource under `data`
  (`{"data": {...}}`); `DELETE` endpoints return a message envelope
  (`{"data": {"message": "...", "id": "..."}}`).
- `POST /parent-child` (201) additionally returns an **optional** `meta.warning`
  when the link is created despite a non-fatal advisory (e.g. an unusual age
  gap) — omitted entirely when there's nothing to warn about:
  ```json
  { "data": { "id": "...", "parent_id": "...", "child_id": "...", "...": "..." },
    "meta": { "warning": "..." } }
  ```

## Versioning & Compatibility Rules
- Any rule tightening that can reject previously accepted writes is a behavior-breaking change.
- Document behavior-breaking changes in a new ADR and release notes.
- Keep response and error envelopes stable across versions.
