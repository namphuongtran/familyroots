# File Storage

How document/photo blobs are stored in Supabase Storage: one shared bucket,
path-based clan isolation, presigned reads, and hard deletes.

> ⚠️ **Deletion is permanent.** `DELETE /documents/{id}` hard-deletes the DB row and
> permanently removes the blob — there is **no trash, no soft delete, no versioning**.
> And the "orphan sweep" referenced in code comments **does not exist yet**: orphaned
> blobs (from failed compensations) are only logged, never reclaimed. Both are
> data-safety gaps — see [ops/backup-restore.md](../ops/backup-restore.md).

## Bucket layout & isolation

Single bucket **`family-roots-files`** (`SUPABASE_STORAGE_BUCKET`), isolated by path
prefix — the storage arm of [multi-tenancy](multi-tenancy.md):

```
family-roots-files/
└── clans/{clan_id}/documents/{file_uuid}.{ext}
```

The key is built server-side in `DocumentCommandHandler.upload`
(`backend/app/application/document/handlers.py`); the extension is sanitized by
`_safe_extension` (lowercase alphanumerics only) so a hostile filename like
`x.jpg/../../other-clan/evil` cannot escape the clan prefix.

All storage calls go through the **service-role Supabase client**
(`app/infrastructure/supabase_client.py`), which **bypasses RLS** — bucket policies do
not protect anything here; isolation is enforced by the application building the path
and by clan-scoped repository reads.

## Upload flow

`POST /api/v1/documents` (editor+) → `app/api/v1/documents.py`:

1. Route reads at most `max_upload_bytes + 1` bytes (bounds the in-RAM copy; the `+1`
   still trips the size check). NOTE: the multipart parser has already spooled the full
   body to a temp file — a hard total-body limit belongs at the proxy/ASGI layer.
2. `Document.create` (**domain**, `app/domain/document/entity.py`) validates:
   - MIME against `ALLOWED_MIME_TYPES` (jpeg/png/webp/heic, pdf, mpeg/wav audio,
     mp4/quicktime video) → `invalid_mime_type`;
   - size against the injected limit → `file_too_large`. Default 50 MB
     (`DEFAULT_MAX_FILE_SIZE_BYTES`), env-tunable via `MAX_UPLOAD_SIZE_MB`.
3. **Blob first, then metadata** — with compensation: if the DB save/commit fails, the
   just-uploaded blob is deleted (best-effort) before re-raising, so neither an orphan
   blob nor a dangling row survives. A failed cleanup logs
   `Orphaned blob after failed upload commit`.

## Presigned URL flow

Blobs are never public; reads go through time-limited signed URLs:

- `GET /documents/{id}` and the upload response include `presigned_url` +
  `presigned_url_expires_at`.
- TTL constant: **`DEFAULT_PRESIGN_TTL = 3600` seconds** in
  `app/domain/document/repository.py` (the port owns the default).
- Avatar presigns are the exception: `set_avatar` returns a **30-day** URL
  (`expires_in=86400 * 30`) since clients cache avatars.

## Avatar flow

`PATCH /documents/{id}/set-avatar` (editor+): only a `photo` document linked to a
person can be an avatar; previous avatars for that person are cleared in the same
transaction. The DB commit happens **before** the presign — a storage outage yields
`presigned_url: null`, never a 503 on a pure-DB write.

## Delete flow

`DELETE /documents/{id}` (admin only) is **DB-first**: commit the row removal, then
remove the blob. If the storage delete then fails, the blob is merely orphaned
(logged; reclaimable only by the not-yet-built sweep) — the reverse order could roll
back the row after the blob was already gone.

## StorageError taxonomy → HTTP

`SupabaseStorageAdapter` (`app/infrastructure/storage/supabase_adapter.py`) classifies
every SDK/transport failure into the domain taxonomy
(`app/domain/document/repository.py`); handlers in `app/core/exceptions.py` map them:

| Error | Meaning | HTTP |
|---|---|---|
| `StorageNotFoundError` | Object missing in the bucket | 404 `storage_not_found` |
| `StorageUnavailableError` | Provider 5xx, transport failure, rejected API key | 503 `storage_unavailable` |
| unexpected 4xx (e.g. duplicate key) | Code bug — stays loud | 500 |

The blocking `storage3` SDK is offloaded with `asyncio.to_thread` so it never freezes
the event loop. `delete()` alone never raises (it runs post-commit as compensation).

## Related

- [Multi-Tenancy](multi-tenancy.md) — path prefix as the storage tenancy boundary
- [ops/configuration.md](../ops/configuration.md) — `MAX_UPLOAD_SIZE_MB`, bucket name
- [ops/backup-restore.md](../ops/backup-restore.md) — blob backup + hard-delete gap
