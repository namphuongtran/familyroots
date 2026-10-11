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
- POST /uploads  (editor+) — sign a direct-to-Storage upload, see below
- POST /  (editor+) — confirm a staged upload as a document, see below
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
That covers `POST /` (confirm), `GET /{id}`, and `POST /{id}/restore`. Clients
schedule refreshes off this timestamp instead of hardcoding the TTL. Corrected
2026-08-02: `GET /{id}` and restore previously returned `null` here while still
returning a fresh URL.

`GET /` (list) returns summaries with neither a URL nor an expiry.

### Upload: sign, PUT to Storage, confirm (ADR-068)

A document's bytes never pass through the API. On Vercel a request body over 4.5 MB is refused
with Vercel's own 413, which carries no error envelope (ADR-065), so the browser sends the file
straight to Supabase Storage. The limit is `MAX_UPLOAD_SIZE_MB`, 50 MB by default. Three steps:

**1. `POST /documents/uploads`** (editor+), JSON body:

```json
{ "filename": "gia-pha.jpg", "content_type": "image/jpeg", "size_bytes": 2048000 }
```

| Field | Rule |
|---|---|
| `filename` | 1 to 255 characters. Only its extension is kept, sanitised to lowercase alphanumerics, `bin` when there is none |
| `content_type` | 1 to 100 characters, and one of the approved types: `image/jpeg`, `image/png`, `image/webp`, `image/heic`, `application/pdf`, `audio/mpeg`, `audio/wav`, `video/mp4`, `video/quicktime` |
| `size_bytes` | at least 0, at most the limit |

These are declarations, checked before any byte is sent: `422 invalid_mime_type` or
`422 file_too_large`. On success, 200:

```json
{
  "data": {
    "storage_path": "clans/{clan_id}/uploads/{uuid}.jpg",
    "upload_url": "https://<project>.supabase.co/storage/v1/object/upload/sign/family-roots-files/clans/{clan_id}/uploads/{uuid}.jpg?token=…",
    "token": "…",
    "expires_at": "2026-10-11T12:00:00Z"
  }
}
```

`expires_at` is two hours out, the lifetime Supabase fixes for a signed upload URL.

**2. `PUT upload_url`**, to Storage, not the API. The body is the file, with `Content-Type`
equal to the declared type. Send no `Authorization` header: the signed URL is the whole
authorization for this one upload. Storage answers 200. It refuses a type outside the bucket's
`allowed_mime_types` (415 `InvalidMimeType`), a file over the bucket's limit, and a second PUT to
the same path (409 `KeyAlreadyExists`).

**3. `POST /documents`** (editor+), JSON body:

| Field | Rule |
|---|---|
| `storage_path` | required, exactly as step 1 returned it |
| `title` | required, 1 to 255 characters |
| `document_type` | required, `photo`, `id_document`, `certificate`, `audio`, `video` or `other` |
| `original_filename` | optional, at most 255 characters |
| `person_id` | optional, a person of the acting clan |
| `description`, `taken_date`, `taken_place` | optional; `taken_place` at most 255 characters |

The API then reads what Storage actually holds. A file whose stored type or size breaks the rule
is **deleted** and refused, so it can never be confirmed later. A missing type is refused too.
Otherwise the file moves to `clans/{clan_id}/documents/{uuid}.{ext}` and the row is saved: 201
with the same `DocumentResponse` as every other route, its `storage_path` the `documents/` one
and its `mime_type` and `file_size_bytes` what Storage recorded.

| Status | Code | When | The staged file |
|---|---|---|---|
| 422 | `document.upload_path_invalid` | `storage_path` is not a staged path of the acting clan: another clan's, a `documents/` path, a traversal, any other shape | untouched |
| 404 | `document.upload_not_found` | nothing is stored there: never uploaded, already confirmed, or swept | — |
| 404 | `person_not_found` | `person_id` is not a person of the acting clan | kept, so the call can be retried |
| 422 | `invalid_mime_type` | the stored type is missing or not approved | deleted |
| 422 | `file_too_large` | the stored size is over the limit | deleted |
| 422 | `validation_error` | a field above breaks its rule | kept |

A second confirm of one path answers `404 document.upload_not_found` and makes no second row.
A staged file nobody confirms is deleted by the retention purge after 24 hours (below).

### Storage errors on the routes that mint a presigned URL

`POST /uploads` signs a path in the private bucket (`SUPABASE_STORAGE_BUCKET`). `POST /`
reads the staged object, moves it, and then mints a presigned URL. `GET /{id}` and
`POST /{id}/restore` only mint the URL. Each can answer:

| Status | Code | When |
|---|---|---|
| 404 | `storage_not_found` | The document's object is missing from the bucket |
| 503 | `storage_bucket_not_configured` | The bucket itself is missing or unreachable with the server's key — an operator action, not the caller's fault (#177) |
| 503 | `storage_unavailable` | Provider outage, transport failure, or a rejected key |

**A 503 does not always mean nothing happened.** `POST /` and `POST /{id}/restore`
commit their row **before** they mint the URL. So a 503 from the URL step arrives
after the write: the document exists, or is restored, but the response carries no
URL. Do not retry those two blindly. Re-read with `GET /` or `GET /{id}` first. A retried
confirm answers `404 document.upload_not_found`, because its staged file has already moved, and
a retried restore answers `404 document_not_found`. A missing bucket fails the confirm at its
first Storage read, before any row is written, so `storage_bucket_not_configured` on `POST /`
means nothing was saved; on restore it means the restore went through. `POST /uploads` writes
nothing and is safe to retry. `GET /{id}` writes nothing and is safe to
retry once the cause is fixed.

`GET /` (list) mints no URL and touches no blob. Set-avatar's own storage errors are
in its section below, and the JSON export's in [rest-exports-api.md](rest-exports-api.md).

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

A missing bucket is **not** "blob already gone": if `SUPABASE_STORAGE_BUCKET`
names a bucket that does not exist, the purge removes nothing and every eligible
row survives to the next run (#177). Before that fix the job read Supabase's
"Bucket not found" as a missing object and purged the rows, leaving their blobs
in the real bucket for ever.

The same run also deletes every **staged upload** older than 24 hours: a file under
`clans/{clan_id}/uploads/` that was signed, maybe uploaded, and never confirmed (ADR-068). Confirm
moves a file out of that folder, so a confirmed document's blob is never touched by this sweep.

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
| 422 | `document.avatar_mime_type_not_allowed` | The document's declared `mime_type` is not `image/jpeg`, `image/png`, `image/webp` or `image/heic`, **including no `mime_type` at all**. A "photo" label does not make a PDF an image (#176). `detail`: `mime_type` (the declared value or `null`), `allowed` (list) |
| 422 | `document.avatar_source_outside_clan` | Clan backstop: the document's storage key is not under the acting clan's prefix |
| 422 | `person.avatar_url_not_permanent` | The publish returned a non-permanent URL (a signed/expiring one). Server-side invariant; should never reach a client |
| 503 | `storage_bucket_not_configured` | The public avatars bucket is missing, unreachable, or not public-read; or the private documents bucket the photo is copied from is missing (#177). An operator action, see [storage.md](../architecture/storage.md) |
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
- **`POST /` stopped taking multipart on 2026-10-11 (ADR-068, #256), a breaking change shipped
  without a version bump.** It takes JSON naming a staged path that `POST /uploads` signed. The
  web was the only caller and moved in the same pull request; mobile has no upload. The response
  is unchanged. The limit went from production's 4 MB to 50 MB.
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
- `PATCH /{id}/set-avatar` refuses a "photo" whose declared `mime_type` is not one of
  the four image types with `422 document.avatar_mime_type_not_allowed` (#176). Before
  that, a PDF, audio or video file labelled "photo" was published into the
  world-readable avatars bucket. This is a new failure mode, not a shape change. On
  2026-10-04 no web or mobile code called this endpoint (only the generated
  `web/src/generated/api-types.ts` names it). Upload is unchanged: a PDF can still be
  uploaded as a "photo", it just cannot become an avatar.
- A missing **private** bucket answers `503 storage_bucket_not_configured` on `POST /`,
  `GET /{id}`, `POST /{id}/restore` and set-avatar (#177). It used to answer
  `404 storage_not_found`, which told the client its document was gone. Same envelope,
  a different code and status for a server misconfiguration only; a genuinely missing
  object is still `404 storage_not_found`.
