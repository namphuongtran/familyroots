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

### Presigned URLs always state their expiry

Every response that includes a `presigned_url` also includes
`presigned_url_expires_at` — an absolute, timezone-aware UTC timestamp equal to
the moment the URL was minted plus the presign TTL (`DEFAULT_PRESIGN_TTL`, 3600 s).
That covers `POST /` (upload), `GET /{id}`, and `POST /{id}/restore`. Clients
schedule refreshes off this timestamp instead of hardcoding the TTL. Corrected
2026-08-02: `GET /{id}` and restore previously returned `null` here while still
returning a fresh URL.

`GET /` (list) returns summaries with neither a URL nor an expiry.

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
(including a fresh `presigned_url` + its `presigned_url_expires_at`) on
success; 404 `document_not_found` if
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
does not clear `is_avatar`, and since ADR-036 it does not affect the person's
`avatar_url` either — the published public object survives soft-delete **and**
the purge. See the warning in "Set avatar" below.

### `PATCH /{id}/set-avatar` (editor+) — ADR-036

Publishes the photo to the **public avatars bucket** and stamps the resulting
permanent URL onto `persons.avatar_url`. This endpoint is the only writer of that
column; `PATCH /persons/{id}` rejects it (see
[rest-persons-api.md](rest-persons-api.md)).

Response (200) — `avatar_url` is **new and additive**:

```json
{
  "data": {
    "message": "Đã đặt ảnh đại diện",
    "document_id": "…",
    "avatar_url": "https://<project>.supabase.co/storage/v1/object/public/family-roots-avatars/clans/<clan_id>/avatars/<person_id>"
  }
}
```

The URL is **permanent and unauthenticated**: no expiry, no query string, no token,
readable by anyone who has it regardless of clan or login. Cache it, store it, render
it in an `<img src>` — it will not expire. It is the same value that now appears as
`avatar_url` on person, tree, search and event responses. Because the object path is
stable per person, replacing an avatar **reuses the same URL**; expect up to
`AVATAR_CACHE_CONTROL_SECONDS` (default 300 s) of staleness after a change, and prefer
a cache-busting query parameter on the client if you need an instant swap.

Errors:

| Status | Code | When |
|---|---|---|
| 404 | `document_not_found` | Not this clan's document, or soft-deleted |
| 404 | `person_not_found` | The linked person is not a live member of the acting clan |
| 422 | `document_not_linked_to_person` | The document has no `person_id` |
| 422 | `only_photo_can_be_avatar` | `document_type != "photo"` |
| 422 | `document.avatar_source_outside_clan` | Clan backstop: the document's storage key is not under the acting clan's prefix |
| 422 | `person.avatar_url_not_permanent` | The publish returned a non-permanent URL (a signed/expiring one). Server-side invariant; should never reach a client |
| 503 | `storage_bucket_not_configured` | The public avatars bucket is missing, unreachable, or not public-read — an operator action, see [storage.md](../architecture/storage.md) |
| 503 | `storage_unavailable` | Provider outage during the copy |

**Behaviour change:** set-avatar is no longer a pure-DB write. It previously committed
first and tolerated a storage outage; it now publishes a blob, so on any storage
failure it returns 503 and the avatar is **not** set (nothing half-applied). It also no
longer mints the 30-day presigned URL it used to compute and discard.

> ⚠️ Publishing an avatar is currently **irreversible from the API**. `DELETE
> /{id}` (soft delete) and the retention purge remove only the private blob; the
> published public object and `persons.avatar_url` are left in place, so anyone holding
> the URL keeps access. Tracked as a follow-up in ADR-036 "Known gaps".

## Versioning & Compatibility Rules
- Adding optional metadata fields is non-breaking.
- Changing upload requirements or allowed MIME sets is breaking.
- Keep presigned URL and delete/restore semantics stable.
- `DELETE`'s response shape (200, `{"data": {"message", "id"}}`) is frozen even
  though its underlying effect changed from hard- to soft-delete — this was a
  behavior change, not a contract change, and shipped without a version bump.
- `PATCH /{id}/set-avatar` gained `data.avatar_url` (additive, non-breaking) and can
  now return 503 where it previously always succeeded on the DB write. Existing
  clients that only read `message`/`document_id` are unaffected apart from the new
  failure mode (ADR-036).
