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

**Two buckets, with opposite visibility.** Both are isolated by path prefix — the
storage arm of [multi-tenancy](multi-tenancy.md) — but only the first is private:

```
family-roots-files/                                 # PRIVATE  (SUPABASE_STORAGE_BUCKET)
└── clans/{clan_id}/documents/{file_uuid}.{ext}

family-roots-avatars/                               # PUBLIC   (SUPABASE_AVATAR_BUCKET)
└── clans/{clan_id}/avatars/{person_id}             # no extension; Content-Type carries the format
```

Keeping them apart is load-bearing: it is what stops "avatars are public" (ADR-036)
from making every certificate, ID document and audio recording public too. Never point
`SUPABASE_AVATAR_BUCKET` at `SUPABASE_STORAGE_BUCKET`.

The document key is built server-side in `DocumentCommandHandler.upload`
(`backend/app/application/document/handlers.py`); the extension is sanitized by
`_safe_extension` (lowercase alphanumerics only) so a hostile filename like
`x.jpg/../../other-clan/evil` cannot escape the clan prefix. The avatar key is built by
`_avatar_object_path` from the authenticated clan id and the document's person link —
both server state, so there is nothing to sanitize — and is stable per person, so
replacing an avatar upserts the same object and the stored URL never changes.

All storage calls go through the **service-role Supabase client**
(`app/infrastructure/supabase_client.py`), which **bypasses RLS** — bucket policies do
not protect anything on the write side; isolation is enforced by the application
building the path and by clan-scoped repository reads. On the *read* side the two
buckets differ absolutely: `family-roots-files` is unreadable without a presign, while
anything in `family-roots-avatars` is readable by anyone with the URL, forever, with no
authentication and no clan check. See ADR-036's Consequences.

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
- **Avatars do not use presigns at all** (ADR-036). `set_avatar` used to mint a 30-day
  URL and throw it away; it now publishes to the public bucket instead. A presigned URL
  must never be stored in `persons.avatar_url` — `Person.set_avatar_url` rejects any URL
  with a query string precisely to make that impossible.

## Avatar flow (ADR-036)

`PATCH /documents/{id}/set-avatar` (editor+) is the **only** writer of
`persons.avatar_url`. Clients cannot write that column: it is rejected with 422 by the
person write schemas and is absent from the Person aggregate's updatable-field
whitelist and from the `CreatePerson` command.

Sequence (`DocumentCommandHandler.set_avatar`):

1. Load the document clan-scoped; `Document.set_avatar()` validates it is a `photo`
   linked to a person.
2. **Clan backstop**: the document's `clan_id` and its storage key prefix must both
   match the acting clan, else `422 document.avatar_source_outside_clan`. A public
   bucket is the last place to discover an isolation mistake.
3. Load the person clan-scoped (not a member → `404 person_not_found`).
4. Release the pooled DB connection (ADR-028), then **copy** the image into
   `family-roots-avatars/clans/{clan_id}/avatars/{person_id}` with `upsert=true` and
   `Cache-Control: max-age=AVATAR_CACHE_CONTROL_SECONDS`.
5. Stamp the resulting permanent URL via `Person.set_avatar_url` (emits
   `PersonUpdated`), clear the person's previous avatar documents, and commit — one
   transaction, two audit rows: `document.set_avatar` and `person.update`.

The response now returns `avatar_url` alongside `message`/`document_id`.

**Failure is closed, and that is a change.** The publish gates the DB write, so a
storage failure means the avatar is simply not set. Previously set-avatar was a pure-DB
write that tolerated a storage outage; it cannot be now, because `is_avatar = true`
with no reachable object is a half-applied state with a permanently wrong URL attached
to a person.

### Operator setup — the public bucket does not exist until someone creates it

`SUPABASE_AVATAR_BUCKET` (default `family-roots-avatars`) must be created by hand in
the Supabase dashboard, per environment. Until it is, every set-avatar call returns
`503 storage_bucket_not_configured` and nothing is written.

| Setting | Value |
|---|---|
| Name | `family-roots-avatars` (must match `SUPABASE_AVATAR_BUCKET`, must differ from `SUPABASE_STORAGE_BUCKET`) |
| Public bucket | **on** — public read. The adapter verifies this before copying and refuses if it is off. |
| Allowed MIME types | `image/jpeg, image/png, image/webp, image/heic` |
| File size limit | ≥ `MAX_UPLOAD_SIZE_MB` (default 50 MB) |
| Write access | service-role key only (the backend already has it); add no anonymous write policy |

- **Cache-Control** is set per object by the backend to
  `max-age=AVATAR_CACHE_CONTROL_SECONDS` (default 300 s). Because the object path is
  stable per person, a replaced avatar keeps its URL — this window is how long a stale
  portrait can still be served from a cache.
- **CORS**: not required. Clients render avatars with `<img src>`, which needs none.
  Add an allow-list of web/mobile origins only if a client starts reading avatar bytes
  via `fetch`/XHR.

> ⚠️ **Publishing an avatar is effectively irreversible today.** `DELETE /documents/{id}`
> is a soft delete and the retention purge removes only the *private* blob; no code path
> deletes the published public object or clears `persons.avatar_url`. Anyone who has the
> URL keeps working access after the document is deleted. Closing this is a tracked
> follow-up (ADR-036, "Known gaps").

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
| `StorageBucketNotConfiguredError` | Target bucket missing, unreachable, or not public-read | 503 `storage_bucket_not_configured` |
| unexpected 4xx (e.g. duplicate key) | Code bug — stays loud | 500 |

`StorageBucketNotConfiguredError` (ADR-036) is deliberately flat — a direct subclass of
`StorageError`, not of the other two — so Starlette's MRO lookup cannot let
registration order decide which envelope a misconfigured bucket produces. It is a
distinct code because a missing bucket is an infrastructure gap an operator must close,
not a transient outage to retry (`storage_unavailable`) and not the caller's missing
object (`storage_not_found`). Supabase reports a missing bucket as a 400/404 saying
"Bucket not found", which the generic classifier would otherwise read as a missing
*object*; `_classify_bucket` catches that first.

The blocking `storage3` SDK is offloaded with `asyncio.to_thread` so it never freezes
the event loop.

## Related

- [ADR-019](../decisions/019-document-soft-delete-purge.md) — soft-delete +
  retention purge decision, crash-safety analysis, deferred orphan
  reconciliation
- [notifications-scheduler.md](notifications-scheduler.md) — `document_purge`
  job schedule and lock topology
- [ADR-036](../decisions/036-public-avatar-urls.md) — permanent public avatar URLs:
  the decision, the operator's bucket checklist, and the privacy trade-off
- [ops/configuration.md](../ops/configuration.md) — `MAX_UPLOAD_SIZE_MB`,
  `DOCUMENT_RETENTION_DAYS`, bucket names, `AVATAR_CACHE_CONTROL_SECONDS`
- [Multi-Tenancy](multi-tenancy.md) — path prefix as the storage tenancy boundary
- [ops/backup-restore.md](../ops/backup-restore.md) — blob backup gap (orphan
  reconciliation still deferred)
