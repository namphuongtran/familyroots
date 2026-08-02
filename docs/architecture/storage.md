# File Storage

How document/photo blobs are stored in Supabase Storage: one shared bucket,
path-based clan isolation, presigned reads, and a soft-delete → retention →
purge lifecycle.

## Delete lifecycle (ADR-019)

`DELETE /documents/{id}` (admin) is a **soft-delete**: the row is flagged
(`is_deleted=true`, `deleted_at`/`deleted_by` stamped) and the blob is left
completely untouched. Reads/lists filter `is_deleted = false`, so the document
disappears from the app immediately while its blob remains downloadable via
presign for up to `DOCUMENT_RETENTION_DAYS` (default 30) days. `POST
/documents/{id}/restore` (admin) reverses this — a pure metadata flip, no
storage round-trip, since the blob was never removed.

A daily retention purge job (`app/services/document_purge.py`, see
[notifications-scheduler.md](notifications-scheduler.md)) permanently removes
documents whose `deleted_at` is older than the retention window: **claim the
row (guarded `DELETE ... WHERE is_deleted=true AND deleted_at<cutoff`) →
delete the blob → commit**, in that order, so a crash anywhere rolls back the
claim and the row survives to retry — never a silent partial purge, never an
orphan blob left by *this* code path. Full crash-safety analysis and the
per-item error-isolation guarantees are in
[ADR-019](../decisions/019-document-soft-delete-purge.md).

> ⚠️ **Still deferred**: orphan-blob reconciliation for blobs that predate this
> lifecycle or come from a failed upload compensation (see the upload-flow
> note below) — those are only logged, never reclaimed; needs bucket-listing
> pagination, tracked as a follow-up. See
> [ops/backup-restore.md](../ops/backup-restore.md).

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

- `GET /documents/{id}`, the upload response, and `POST /documents/{id}/restore`
  include `presigned_url` + `presigned_url_expires_at` (computed by
  `_presign_expiry()` in `app/application/document/handlers.py` — one helper, so a
  URL-bearing response can never again ship without its deadline).
- TTL constant: **`DEFAULT_PRESIGN_TTL = 3600` seconds** in
  `app/domain/document/repository.py` (the port owns the default).
- Avatar presigns are the exception: `set_avatar` returns a **30-day** URL
  (`expires_in=86400 * 30`) since clients cache avatars.

## Avatar flow

`PATCH /documents/{id}/set-avatar` (editor+): only a `photo` document linked to a
person can be an avatar; previous avatars for that person are cleared in the same
transaction. The DB commit happens **before** the presign — a storage outage yields
`presigned_url: null`, never a 503 on a pure-DB write.

## Delete flow (`DELETE /documents/{id}`, admin only)

As of ADR-019, `DELETE` is a metadata-only soft-delete (see "Delete lifecycle"
above) — it never touches the blob. The blob is only ever removed by the
retention purge job, well after the row is claimed inside its own transaction
(claim → delete blob → commit). There is no more DB-first-then-blob ordering
in the request path at all; that ordering question moved entirely into the
purge job.

## `StoragePort.delete()` contract (changed under ADR-019)

`StoragePort.delete()` (`app/domain/document/repository.py`) returns `True`
when the object was deleted **or is confirmed already absent** (idempotent —
a missing object is not a failure), and **raises** the classified
`StorageError` for anything where deletion could not be confirmed either way.
This is stricter than delete's old "never raises, best-effort compensation"
behavior: the purge job's row-claim commit is gated on this call succeeding,
so an unconfirmed failure must surface as an exception — a swallowed
`False`/`True` could let a row be purged while its blob deletion is genuinely
unconfirmed. `SupabaseStorageAdapter.delete()` implements this by classifying
`StorageNotFoundError` as success (`True`) and re-raising everything else.

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
the event loop.

## Related

- [ADR-019](../decisions/019-document-soft-delete-purge.md) — soft-delete +
  retention purge decision, crash-safety analysis, deferred orphan
  reconciliation
- [notifications-scheduler.md](notifications-scheduler.md) — `document_purge`
  job schedule and lock topology
- [ops/configuration.md](../ops/configuration.md) — `MAX_UPLOAD_SIZE_MB`,
  `DOCUMENT_RETENTION_DAYS`, bucket name
- [Multi-Tenancy](multi-tenancy.md) — path prefix as the storage tenancy boundary
- [ops/backup-restore.md](../ops/backup-restore.md) — blob backup gap (orphan
  reconciliation still deferred)
