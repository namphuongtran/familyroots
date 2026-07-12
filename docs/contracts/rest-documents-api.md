# Contract: documents-api

## Type
REST API

## Owner
backend

## Consumers
- web
- mobile

## Schema
Base route: /api/v1/documents

Core operations:
- POST /
- GET /  (cursor-paginated; query params: cursor, limit, person_id, document_type, fields)
- GET /{id}
- DELETE /{id}  (admin) — **soft-delete**, see below
- POST /{id}/restore  (admin)
- PATCH /{id}/set-avatar

List response envelope (cursor pagination):
```
{
  "data": [ ... ],
  "meta": { "cursor": "<base64|null>", "has_more": true, "limit": 20 }
}
```
- `meta.cursor` is null on the last page; pass it back as `?cursor=` to fetch the next.

Upload expectations:
- multipart/form-data upload
- file, title, document_type required
- person_id, description, taken_date, taken_place optional
- supports approved media and document MIME types

### Delete is soft, with a restore window (ADR-019)

`DELETE /{id}` (admin) no longer removes the row or the blob. It calls the
entity's `mark_deleted(actor)`: `is_deleted=true`, `deleted_at`/`deleted_by`
stamped, blob untouched. Response shape is unchanged (`{"data": {"message":
"Document deleted", "id": "..."}}`, 200) — only the underlying semantics
changed.

`GET /`, `GET /{id}` (via list/detail queries) and all list filters only ever
return `is_deleted = false` rows — a soft-deleted document disappears from
reads immediately, exactly as if it had been hard-deleted, while its blob
remains presignable until the retention purge removes it.

`POST /{id}/restore` (admin, new): 200 with the full `DocumentResponse`
(including a fresh `presigned_url`) on success; 404 `document_not_found` if
the document doesn't exist or isn't currently soft-deleted (mirrors
`POST /persons/{id}/restore`). Restoring is a pure metadata flip — no storage
round-trip, since the blob was never touched by delete.

### Retention purge

A daily job (`document_purge`, see
[notifications-scheduler.md](../architecture/notifications-scheduler.md))
permanently removes the row **and** the blob once `deleted_at` is older than
`DOCUMENT_RETENTION_DAYS` (default 30 — see
[ops/configuration.md](../ops/configuration.md)). After that window, restore
returns 404 like any other missing document — there is no recovery once the
purge has run for that row. See [ADR-019](../decisions/019-document-soft-delete-purge.md)
for the full claim-row → delete-blob → commit ordering and crash-safety
analysis.

Avatar interplay: soft-deleting a document currently set as a person's avatar
does not clear `is_avatar` and does not break the avatar's presigned URL until
the blob is actually purged — accepted v1 behavior (ADR-019).

## Versioning & Compatibility Rules
- Adding optional metadata fields is non-breaking.
- Changing upload requirements or allowed MIME sets is breaking.
- Keep presigned URL and delete/restore semantics stable.
- `DELETE`'s response shape (200, `{"data": {"message", "id"}}`) is frozen even
  though its underlying effect changed from hard- to soft-delete — this was a
  behavior change, not a contract change, and shipped without a version bump.
