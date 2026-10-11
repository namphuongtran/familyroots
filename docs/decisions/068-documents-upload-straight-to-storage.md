# ADR-068: Documents Upload Straight to Storage

## Status

Accepted, shipped (2026-10-11). Resolves issue #256, "Documents upload straight to Storage, and
the 4 MB cap becomes 50 MB".

The maintainer settled the decisions below in the triage of #256 on 2026-10-11. **This ADR ships
with its code**, in the same pull request. It amends [ADR-065](065-the-backend-runs-on-vercel-functions.md)
§ 6, which capped uploads at 4 MB and deferred this work, and
[ADR-019](019-document-soft-delete-purge.md), whose purge job now also sweeps the staging folder.
Both carry a dated amendment in their Status.

## Context

- **Vercel refuses a request body over 4.5 MB before it reaches the app**, with its own
  `413 FUNCTION_PAYLOAD_TOO_LARGE`, which carries no error envelope (ADR-065). Measured on
  2026-10-11 against a throwaway project: a 4 MiB POST reached FastAPI and a 5 MiB one got the
  413 (#271).
- **`POST /documents` proxied the file bytes through the Function**, so ADR-065 § 6 capped
  uploads at 4 MB in the web client and in production's `MAX_UPLOAD_SIZE_MB`. The domain's
  limit and the bucket's are 50 MB.
- **storage3 2.31.0 can sign an upload**, `create_signed_upload_url(path, options)`, but its only
  option is `upsert`. A signed URL carries no type or size limit.
- **Read on the local stack on 2026-10-11:**
  - A raw PUT to the signed URL needs no API key, so the browser needs nothing but the URL.
  - `info()` returns the stored `size` and `content_type`.
  - A second PUT to the same signed path answers 409 `KeyAlreadyExists`.
  - `move()` works within the bucket, and the source then reads 404.
  - Listing `clans` returns one folder entry per clan, with `id: null`.

## Decision

### 1. Multipart is replaced, not kept beside the new flow

The web is the only consumer of `POST /documents`, and mobile has no upload. Keeping multipart
would keep a second validation path still capped at 4 MB. In the minute between the API deploy
and the web deploy in `release.yml`, an old web's upload fails. That is accepted.

### 2. Two calls: sign, then confirm

- **`POST /documents/uploads`** (editor or above) takes `{filename, content_type, size_bytes}`.
  It answers `{"data": {storage_path, upload_url, token, expires_at}}`. `expires_at` is two
  hours out, the lifetime Supabase fixes for a signed upload URL.
- **The browser PUTs the file to `upload_url`.** It sends no session token, because the signed
  URL is the whole authorization for that one upload.
- **`POST /documents`** (editor or above) keeps its meaning, "create a document". Its body is
  now JSON: `{storage_path, title, document_type, original_filename?, person_id?, description?,
  taken_date?, taken_place?}`. It answers 201 with the same `DocumentResponse` as before.

`original_filename` was not in the issue's list. Without it the confirm call would lose the name
the multipart upload used to record, so it was added as an optional field.

### 3. A staged file waits in its own folder

Sign builds `clans/{acting clan}/uploads/{uuid}.{ext}`. The extension is sanitised exactly as
before, by `storage_paths.safe_extension`. Confirm moves the file to
`clans/{clan}/documents/{same uuid}.{ext}`. No table holds the staged state.

### 4. Confirm trusts a path by its exact shape and by Storage

`parse_staged_upload_path` refuses anything but
`^clans/{acting clan}/uploads/{uuid}\.[a-z0-9]{1,10}$`:
- another clan's prefix;
- a `documents/` path;
- a traversal segment;
- an upper-case or non-canonical uuid;
- any trailing text.

The refusal is `422 document.upload_path_invalid`. Then `stat()` must find the object, or the
call answers `404 document.upload_not_found`. A second confirm of one path finds nothing,
because the first one moved the file, so it gets that 404 and makes no second row. Two confirms
racing on one path both pass `stat()`, but only one `move()` can succeed, and the loser gets the
same 404. The unique `storage_path` backs both cases.

### 5. The limit is 50 MB

It is the domain's `DEFAULT_MAX_FILE_SIZE_BYTES` and the bucket's `file_size_limit`. The server's
limit stays env-driven through `MAX_UPLOAD_SIZE_MB`, enforced at both sign and confirm. The web's
`MAX_UPLOAD_MB` is 50.

### 6. Type and size are checked three times

1. **At signing**, `check_upload_file` runs against the declared type and size. A file that
   breaks a rule is refused before any byte is sent.
2. **At confirm**, the same rule runs against what `stat()` reads, which is the check that
   counts. A file that fails it is deleted and the call refused. Unlike `Document.create`, the
   rule refuses a missing type, because `create` also builds documents from older rows.
3. **In the bucket**, `family-roots-files` has `allowed_mime_types` equal to
   `ALLOWED_MIME_TYPES`. Read on the local stack: a signed PUT as `text/html` answers
   `415 InvalidMimeType`, and as `image/png` 200.

`tests/unit/test_files_bucket_mime_types.py` fails if the bucket list and the domain set drift
apart.

### 7. Unconfirmed files are swept by the existing purge job

After the documents, `purge_expired_documents` deletes every object under `clans/*/uploads/`
older than `STAGED_UPLOAD_MAX_AGE`, 24 hours, under the same advisory lock. It lists only staging
folders, so it never touches `documents/`. Storage pages its listings, so both levels are paged.
One failed delete never stops the sweep, and a failed listing leaves everything for the next run.

### 8. The deployed reading is the maintainer's, after the release

`familyroots-api` has no Preview environment, so the agent's readings run against the local
Supabase stack. After the release, the maintainer uploads a 20 MB file in production on a
throwaway clan and posts the reading on #256.

## Consequences

- **No document byte passes through the Function**, so Vercel's 4.5 MB request limit no longer
  caps a document.
- **The API never sees the bytes, so it checks what Storage recorded.** That means the
  Content-Type the browser sent, and the size. It sniffs no content, and neither did the
  multipart path.
- **A refused file costs one upload and one delete.** At worst it costs a day in the bucket,
  when the confirm call never comes.
- **Two release steps fall to the maintainer:**
  - remove production's `MAX_UPLOAD_SIZE_MB=4` in Vercel, or set it to 50. Until then the sign
    call refuses anything over 4 MB, with `422 file_too_large` in the envelope;
  - run `supabase seed buckets --linked` so the hosted bucket gets the type list.
- **Orphaned blobs already under `documents/` are still not reconciled**, as ADR-019 deferred.
  The sweep reads only `uploads/`.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep multipart beside the new flow | Two validation paths, one still capped at 4 MB, and the web is the only consumer |
| A server-signed ticket from sign, checked by confirm | Confirm re-reads the stored object anyway. The path rule plus `stat()` gives the same isolation with no secret to manage |
| A `pending_uploads` table | It is state a stateless serverless function does not need, plus a migration and a cleanup of its own |
| Upload straight into `documents/` and reconcile orphans later | Reconciling means diffing every document blob against the rows, which ADR-019 already deferred as too heavy. A staging folder keeps the sweep's listing small |
| supabase-js `uploadToSignedUrl` in the browser | It needs the bucket name in the web. The `upload_url` the server returns already names bucket and token, and a plain `fetch` PUT to it is the same request |
| Raise Vercel's limit | Not possible on any plan |

## Verification

- **Gates.** The backend full quality gate, and the full web gate in `web/CLAUDE.md`.
- **Unit:**
  - `tests/unit/application/test_document_upload_handler.py` covers the handler: the path rule
    case by case, the re-read at confirm, the race, the compensation, and the deadlines;
  - `tests/unit/infrastructure/test_staged_upload_sweep.py` runs the real adapter's listing
    over a fake storage3 client, past one page;
  - `tests/unit/infrastructure/test_storage_error_classification.py` covers sign, stat and
    move.
- **Integration:**
  - `tests/integration/test_document_direct_upload.py` covers each refusal over HTTP against
    real Postgres, read in the response and in the bucket;
  - `tests/integration/test_txn_pool_hygiene.py` checks that no Storage call holds a
    connection (ADR-028);
  - `tests/integration/test_document_purge_job.py` checks that the job sweeps.
- **The real reading.** `web/e2e/auth/document-upload.auth.spec.ts` uploads 20 MB through the
  real screen to the local stack. The API sees two small JSON bodies, Storage answers the PUT
  200, and the presigned URL serves the same bytes by SHA-256.
- **Negative controls**, each run on 2026-10-11 and recorded in the commit messages:
  - clan prefix wildcarded: the cross-clan cases fail with 201;
  - the confirm re-read removed: the type and size cases fail;
  - the sweep pointed at `documents/`: the sweep case fails;
  - the rollback before signing removed: the hygiene case fails;
  - the compensating delete skipped: the commit-failure case fails;
  - the PUT sent through the API: the web transport case fails;
  - the PUT one byte short: the e2e walk fails on the stored size.

## Related

- [ADR-065](065-the-backend-runs-on-vercel-functions.md) § 6, amended 2026-10-11 by this ADR
- [ADR-019](019-document-soft-delete-purge.md), amended 2026-10-11 by this ADR: the purge job
  also sweeps staged uploads
- [ADR-028](028-no-external-io-holding-db-connection.md): no Storage call holds a connection
- [ADR-036](036-public-avatar-urls.md): the avatars bucket, untouched
- [contracts/rest-documents-api.md](../contracts/rest-documents-api.md),
  [architecture/storage.md](../architecture/storage.md)
