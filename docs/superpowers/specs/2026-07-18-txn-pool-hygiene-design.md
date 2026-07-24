# Transaction & Pool Hygiene (A6 / H5) — Design

**Date:** 2026-07-18
**Source finding:** H5 in `docs/architecture/backend-review-2026-07-18.md` — the
LAST High. External Supabase calls run **inside open DB transactions / with a
pooled connection checked out**, and the pool is hardcoded, so a burst of slow
uploads/exports starves connections for every endpoint (including `/health`,
which then 503s and can flap the deploy).
**Owner decision:** upload uses **validate → release → upload → persist**
(over upload-first + compensate).

## The three holes

1. **Document upload** (`application/document/handlers.py:80`): the
   `person_in_clan` SELECT autobegins a transaction on the request session; the
   multi-second Supabase blob upload then runs with that connection **checked
   out and idle-in-transaction**, until the final commit.
2. **Clan export** (`application/export/handlers.py::_presign_manifest`,
   ~:120): after reading everything, it presigns **every document serially**
   while the request session still holds its connection — N sequential network
   round-trips, connection held throughout.
3. **Pool sizing** (`core/database.py:19-27`): `pool_size=10, max_overflow=20`
   hardcoded, not env-tunable; two Render instances → up to ~62 connections vs
   Supabase small-tier's ~60 direct limit, and no headroom math is documented.

## Design (ADR-028: no external I/O while holding a pooled connection)

### 1. Upload — validate → release → upload → persist

```
person_in_clan(person_id, clan_id)   # read; may be None-person_id (skip)
await uow.rollback()                  # END the read txn → connection returns to pool
await storage.upload(path, bytes)     # NO connection held during this
try:
    repo.save(doc); await uow.commit()   # fresh write txn + domain events
except: storage.delete(path) (best-effort); raise   # existing compensation
presigned = await storage.get_presigned_url(path)    # post-commit (see §4)
```

- The read result (a bool / the validation outcome) is captured before the
  rollback; `uow.rollback()` ends the autobegun read transaction cheaply (a read
  has nothing to persist) and returns the connection to the pool. The next
  `repo.save` re-acquires a connection.
- Keeps **validate-before-upload** (a bad/foreign/soft-deleted person_id → 404
  before any blob is written — no wasted upload).
- The existing orphan-blob compensation (delete-on-save-failure) is unchanged.
- `set_avatar`/`restore` in the same handler: audit for the same
  connection-held-during-`get_presigned_url` shape and apply the post-commit /
  no-held-connection discipline where a storage call sits inside a txn (the
  invariant test in §Tests covers every storage call the handler makes).

### 2. Export — read, release, then presign

`export_clan` gathers all rows (persons/edges/events/documents incl. each
document's `storage_path`) from the query port, then — **before** presigning —
ends the read transaction so the session holds no connection during the N
presign round-trips. Mechanism: the export is read-only; after the last
`self._port.*` read, call the port/session's transaction-end (or structure so
the query handler's session commits/rolls-back the read) so `_presign_manifest`
runs with no connection checked out. Presigns may stay serial (correctness
unchanged); the point is **zero connection held** during them.

(If the export query port and the storage presign share one session such that
releasing is awkward, the acceptable alternative is: the query handler returns
all data first (session done), and presigning happens in a separate phase with
no session — decided at implementation against the real DI wiring; the §Tests
invariant is the arbiter.)

### 3. Pool — env-tunable with documented headroom

- `Settings` gains `DB_POOL_SIZE: int = 10`, `DB_MAX_OVERFLOW: int = 20`
  (pydantic-settings, env-overridable). `create_async_engine` reads them.
- Docstring + `docs/ops/configuration.md`: headroom math — per instance max =
  pool_size + max_overflow + (background jobs: scheduler + purge each take a
  dedicated `engine.connect()`); × instance count must stay under the
  Supabase/Render connection ceiling. Default 10+20 unchanged (no behavior
  change out of the box); operators tune per deployment.
- No production fail-fast on pool values (they have safe defaults); just make
  them visible and tunable. `render.yaml` documents the knobs as optional.

### 4. The `/health` + auth-chokepoint interaction (A1 note)

- Not holding connections during external I/O is the actual fix for `/health`
  starvation. `/health` itself is a fast liveness/migration check — verify it
  takes and releases its connection promptly (no change expected, confirm).
- A1 noted `logout`/`PATCH /me` now touch the DB via the `get_current_user`
  chokepoint; under the OLD starvation they could hang. With uploads/exports no
  longer hogging connections, that pressure is relieved — documented as
  resolved-by-A6, no code change.

## What does NOT change

- Upload/export API contracts, response shapes, error codes.
- Orphan-blob compensation semantics (ADR-019 document lifecycle).
- Background jobs' dedicated-connection model (sanctioned; documented in the
  headroom math).
- No migration.

## Tests (real-DB; RED-first — the invariant is "no open txn during external I/O")

The precise, deterministic instrument: a **storage double that captures the
request session's transaction state at call time**. `AsyncSession.in_transaction()`
is True iff a connection is checked out in a live transaction.

1. **Upload invariant** (RED today): a FakeStorage whose `upload()` records
   `session.in_transaction()` when invoked; drive `DocumentCommandHandler.upload`
   over a real session; assert the recorded value is **False** (connection
   released during the blob upload). RED today (the `person_in_clan` read holds
   the txn); GREEN after §1. Also assert `get_presigned_url` was called with the
   session **not** in a transaction.
2. **Upload still correct**: validate-before-upload preserved — bad/foreign/
   soft-deleted person_id → 404 and FakeStorage.upload **never called** (no
   wasted upload); happy path persists + returns presigned url; orphan-blob
   compensation still fires on a save failure (existing test stays green).
3. **Export invariant** (RED today): FakeStorage `get_presigned_url()` records
   `session.in_transaction()`; export a clan with ≥2 documents; assert every
   recorded value is False. RED today; GREEN after §2. Archive content unchanged
   (existing export tests stay green).
4. **Pool tunability**: construct the engine with `DB_POOL_SIZE`/
   `DB_MAX_OVERFLOW` overridden; assert `engine.pool.size()` / `_max_overflow`
   reflect them; a Settings test that the envs parse.
5. **No regression**: full document + export suites green; `/health` test green.

## Docs

- **ADR-028**: the principle (no external network I/O while holding a pooled DB
  connection; connections released across Supabase calls; pool env-tunable) +
  the rejected upload-first alternative + the headroom math.
- `docs/ops/configuration.md`: `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` + headroom math.
- `infra/render/render.yaml`: document the optional pool knobs.
- Grep sweep: `pool_size|max_overflow|idle-in-transaction|presign|connection`
  across docs/contracts + docs/architecture + docs/ops; per-hit dispositions.
