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
  - Query params: cursor, limit, generation, gender, profile, fields, include
- GET /persons/search
  - Query params: q (required, min length 1), limit
- POST /persons
- POST /persons/batch
  - Body: ids (1–100), profile, include, fields, include_by_id (per-person include map)
- GET /persons/{id}
- PATCH /persons/{id}
- DELETE /persons/{id}
- POST /persons/{id}/restore
- POST /persons/{id}/claim
- GET /persons/{id}/marriages
- GET /persons/{id}/parent-child
- GET /persons/{id}/documents
- GET /persons/{id}/events
- GET /persons/{id}/timeline

Response shapes (see [Response envelope](README.md#response-envelope)):

`GET /persons` — cursor-paginated list. **No `total`** — `meta` carries the
cursor triplet only:
```json
{
  "data": [ { "id": "...", "full_name": "...", "...": "..." } ],
  "meta": { "cursor": "opaque-string-or-null", "has_more": false, "limit": 20 }
}
```

`POST /persons/batch` — always 200 even on partial failure; unresolved ids are
reported under `meta.errors`, never mixed into `data`:
```json
{
  "data": [ { "id": "...", "full_name": "...", "...": "..." } ],
  "meta": { "errors": [ { "id": "...", "code": "person_not_found" } ] }
}
```

`POST /persons/{id}/claim` (201):
```json
{ "data": { "id": "...", "status": "PENDING", "...": "..." } }
```

`POST /persons`, `GET /persons/{id}`, `PATCH /persons/{id}` — single resource
under `data`. `DELETE /persons/{id}`, `POST /persons/{id}/restore` — a message
envelope (`{"data": {"message": "...", "id": "..."}}`). `GET
/persons/{id}/{marriages,parent-child,documents,events,timeline}` — a plain
array under `data` (no `meta` — these are not cursor-paginated).

- NOTE: `created_by_clan_id` is **not** accepted on create/update — it is provenance,
  always stamped from the active clan (see the 2026-06-28 design review, C5).

### `avatar_url` is read-only (ADR-036) — **breaking for writers**

`avatar_url` is returned on every person projection (`PersonResponse`, `PersonSummary`,
`PersonMini`, `PersonDetail`, search results) and is **rejected on write**:

- `POST /persons` or `PATCH /persons/{id}` carrying an `avatar_url` key — any value,
  including `null` and `""` — returns **422** `validation_error` with
  `detail.fields` containing `body.avatar_url`. It is *not* silently ignored: a silent
  drop would leave a client believing it had set an avatar.
- This applies to every role. There is no admin or self-edit carve-out.

Set an avatar with **`PATCH /documents/{document_id}/set-avatar`** instead
([rest-documents-api.md](rest-documents-api.md)); that endpoint publishes the image and
returns the permanent URL, which is the same value subsequently echoed here.

The value is a **permanent, unauthenticated public URL** — no expiry, no token,
fetchable by anyone who has it, regardless of clan or login. Safe to cache and persist
on the client. Never construct or guess one; only ever render what the API returned.

Migration for clients that were writing this field: drop `avatar_url` from person
create/update payloads (leaving it in will now fail the whole request), and move the
avatar-setting UI onto the document upload → set-avatar flow.

### Optimistic concurrency (ADR-017)

- Every person response (`GET /persons/{id}`, list/search/batch items, and the
  `PATCH` response) carries `"version": <int>` (≥1), bumped by 1 on every successful
  write to that row — including `DELETE`/`restore`.
- `PATCH /persons/{id}` requires a **required** body field
  `expected_version: int (>=1)` — the `version` value read from a prior
  `GET`/create/PATCH response for this same person. Missing it → standard 422
  Pydantic validation error (`validation_error`).
- If `expected_version` no longer matches the row's current `version` (someone else
  updated/deleted/restored it since your last read) → **409** with code
  `stale_write` and `detail: {"current_version": <int>}`. Client flow: reload the
  person, re-apply the edit on top of the fresh data, resubmit with the new version.
  See [error-codes.md](error-codes.md) and
  [frontend-integration-guide.md §6.1](frontend-integration-guide.md#61-handling-409-stale_write-optimistic-concurrency-adr-017).
- `DELETE /persons/{id}` and `POST /persons/{id}/restore` do **not** require
  `expected_version` (delete/restore are role-gated, soft, and restorable — not the
  same lost-update risk as a field-level PATCH) — but they still bump `version`, so
  a PATCH racing against a delete/restore correctly gets `stale_write` instead of
  silently reverting it.

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
- **2026-08-02 (ADR-036), breaking for writers**: `avatar_url` moved from
  client-writable to server-managed; sending it on create/update is now a 422. It
  remains present and unchanged on every read. Shipped without a version bump because
  no backend code ever populated the field and its meaning was documented as undefined
  — there was no working write behaviour to preserve.
- Non-breaking: add optional fields, add new include profile values, add new optional query params.
- Breaking: remove/rename fields, change required headers, change error envelope.
- Breaking changes require either:
  - additive compatibility period, or
  - new versioned route and migration notice in docs/decisions.
