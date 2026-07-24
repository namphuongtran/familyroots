# ADR-028: No External I/O While Holding a Pooled DB Connection

## Status
Accepted, shipped (2026-07-18, review finding H5).

## Context

The 2026-07-18 backend review (`docs/architecture/backend-review-2026-07-18.md`)
identified **H5**: two write/export paths held a pooled database connection open
across a multi-second **external** network call, and the pool itself was sized
without headroom for the deployment's actual instance count.

- **`DocumentCommandHandler.upload`** (`app/application/document/handlers.py`)
  validated `person_id` against `person_in_clan` — an autobegin read on the
  request's `AsyncSession` — then uploaded the file body to Supabase Storage
  (`self._storage.upload(...)`) **before** touching the DB again. The read
  transaction stayed open (idle-in-transaction) for the entire duration of the
  blob upload: for a large file over a slow client connection, multiple seconds
  with a pooled connection held and doing nothing.
- **`ExportQueryHandler.export_clan`** (`app/application/export/handlers.py`) ran
  every archival read (`clan`, `persons`, `branches`, `marriages`, `parent_child`,
  `generation_map`, `events`, `documents`) on one session, then called
  `_presign_manifest`, which presigns **every document in the clan serially**
  (`app/domain/document/repository.py`'s `StoragePort.get_presigned_url`, one
  Supabase round-trip per document). The request's session — and its pooled
  connection — stayed open for the whole presign loop, proportional to
  documents-per-clan.
- **The pool itself was hardcoded**: `create_async_engine(..., pool_size=10,
  max_overflow=20, ...)` in `app/core/database.py`, with no env override. Two
  Render instances × (10 + 20) = up to **62** connections from the app alone,
  against Supabase's small-tier direct-connection ceiling of roughly **60** —
  before counting the scheduler and document-purge background jobs, each of
  which takes its own dedicated `engine.connect()`
  (`app/services/scheduler.py`, `app/services/document_purge.py`).
- **Net effect**: under concurrent uploads/exports, connections held
  idle-in-transaction through external I/O compounded with a pool ceiling that
  had no slack for the deployment's real instance count and background jobs —
  connection starvation that manifested as `/health` flapping.

## Decision

**No external network I/O while holding a pooled DB connection.** A handler
must release its connection back to the pool before making an external call
whose latency it does not control, and may re-acquire afterward if it still
needs to write.

- **Upload** (`DocumentCommandHandler.upload`): after the `person_in_clan` read
  (and before the Supabase blob upload), call `await self._uow.rollback()` —
  a read-only autobegin has nothing to persist, so rollback is the cheap way to
  end the transaction and release the connection. The blob upload then proceeds
  holding no pooled connection. Persisting the document metadata afterward
  re-acquires a connection for a fresh write transaction, committed normally.
  **Validate-before-upload is preserved**: a bad `person_id` still 404s before
  any bytes are sent to storage — the release just moves the transaction
  boundary, it does not reorder validation after the upload.
- **Export** (`ExportQueryHandler.export_clan`): after the last DB read
  (`documents`) and before `_presign_manifest`'s serial presign loop, call
  `await self._port.release()` — `SqlAlchemyExportQueryPort.release()`
  (`app/infrastructure/persistence/export_query_port.py`) rolls back the
  session (read-only, so rollback is correct), releasing the connection for
  the duration of every presign call.
- **Pool is env-tunable**: `make_engine(settings)` (`app/core/database.py`)
  sources `pool_size`/`max_overflow` from `Settings.DB_POOL_SIZE` /
  `Settings.DB_MAX_OVERFLOW` (`app/core/config.py`), defaulting to `10`/`20` —
  unchanged from the old hardcoded values — so pool sizing can be tuned per
  environment (instance count, provider connection ceiling) without a code
  change or redeploy-from-source.

## Consequences

- **Uploads and exports no longer starve the pool.** A slow blob upload or a
  clan with many documents no longer holds a connection idle for the duration
  of external I/O; the pool has that connection back for other requests.
- **The A1-noted logout/`PATCH /me` chokepoint pressure is relieved by the same
  fix.** Those endpoints touch the DB via `get_current_user`; they were
  competing for pool headroom against connections held by uploads/exports, and
  that competition is what surfaced as `/health` flapping. Releasing the
  held connections relieves that pressure without any change to
  `get_current_user` itself.
- **Validate-before-upload is preserved.** The owner's earlier call — reject a
  bad `person_id` before spending a blob upload on it — still holds; only the
  transaction boundary around that validation moved.
- **Defaults are unchanged.** `DB_POOL_SIZE=10` / `DB_MAX_OVERFLOW=20` match the
  previous hardcoded values, so out-of-box behavior does not change for anyone
  who doesn't set the new env vars.
- **One extra transaction boundary per upload/export.** Upload now does
  rollback → (blob upload) → begin-again-on-write instead of one continuous
  transaction; export does N reads → rollback → presign loop instead of
  N reads held open through presigning. Negligible cost against the seconds of
  held-idle time it eliminates.
- **Regression-guarded.** `backend/tests/integration/test_txn_pool_hygiene.py`
  pins the invariant with a `session.in_transaction()` oracle: it asserts the
  session has no open transaction at the point where external I/O begins, for
  both the upload and export paths.
- **Pool headroom is now an operational tuning knob, not a code change.** See
  `docs/ops/configuration.md` for the headroom formula and Supabase small-tier
  ceiling.
- **Known remaining instance (not closed by this ADR):** `GET /documents/{id}`
  (`DocumentQueryHandler.get`) still runs its `get_presigned_url` while the
  read transaction that fetched the row is open — the same rule as above, but a
  single presign round-trip on a read-only handler (no multi-second body, no
  N-serial loop), so its blast radius is small. It is a genuine remaining
  instance of this rule, deliberately left as a tracked follow-up rather than
  silently treated as resolved by the H5 fix; a future pass should release the
  read before presigning there too (and extend the `session.in_transaction()`
  oracle to that path).

## Alternatives considered

- **Upload-first, then compensate on a bad `person_id`** — rejected: this
  wastes a full blob upload (and a compensating delete) on every invalid-id
  request, purely to avoid moving a transaction boundary. The owner chose to
  keep validate-before-upload and instead release the read transaction before
  the upload, which achieves the same pool-hygiene goal without discarding the
  cheap early rejection.
- **A global connection semaphore/throttle around external I/O** — rejected as
  too blunt: it caps concurrency for uploads/exports uniformly regardless of
  whether a given request is actually holding a connection at that moment,
  and can throttle unrelated traffic under load instead of fixing the actual
  idle-in-transaction behavior.
- **Just raising the pool size** — rejected: it delays when starvation is hit
  but does not fix idle-in-transaction connections held through external I/O;
  at higher concurrency or a bigger document count, the same flapping recurs
  at a higher connection count, and it does nothing for the provider ceiling
  math (more instances or a slow storage provider still exhausts a bigger
  pool). Releasing the connection is the actual fix; the env-tunable pool is
  a complementary knob, not a substitute.
