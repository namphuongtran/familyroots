# Storage Error Taxonomy + Off-load Blocking I/O — Design (2026-07-04)

**Status:** approved (owner) — proceeding to implementation plan.

## Goal

Make the document/storage layer truthful and non-blocking:
1. **Off-load blocking I/O** — the Supabase Storage SDK calls run synchronously inside
   `async def`, freezing the event loop on every upload / delete / presign.
2. **Classify storage errors** — raw SDK exceptions escape as opaque 500s; a storage
   outage/misconfig should be 503 and a missing object 404, mirroring the identity
   provider's taxonomy.
3. Two small correctness fixes in the same area (presign expiry; `set_avatar` ordering)
   and removal of a dead duplicate module.

This is **PR-I** of the demand-driven Important-tier remediation (seam-review §5, S1). It
is scoped to what users hit in normal operation (every upload/push blocks the loop; any
storage hiccup returns a misleading 500) — not speculative work.

## Context — what already exists (do NOT redo)

Handler-level fixes from a prior review already landed on main:
- `DocumentCommandHandler.delete` is **DB-first**: commit the row removal, then best-effort
  storage delete with an orphan-log (S1-1/S1-6 done).
- `upload` has **compensation**: on save/commit failure it best-effort-deletes the blob and
  re-raises (S1-2 done).
- File extension is **sanitized** via `_safe_extension` (S1-9 done).

What remains (this PR): the adapter still calls the sync SDK inline with no error
classification (S1-3, S1-8), the presign expiry is wrong (S1-4), `set_avatar` gates a
pure-DB write on a storage call (S1-5), and `app/services/storage.py` is dead (S1-7).

## Decisions (owner-approved)

- **Off-load mechanism:** `asyncio.to_thread` wrapping the sync SDK calls — minimal change,
  touches only `supabase_adapter.py`, fully resolves the event-loop blocking. (Not migrating
  to the async Supabase client — larger blast radius, over-engineered for the need.)
- **Taxonomy depth:** mirror the identity provider — `StorageUnavailableError` → 503 and
  `StorageNotFoundError` → 404 (not a 503-only simplification).

## Design

### 1. Domain — storage error types (framework-free)
In `app/domain/document/repository.py` (where `StoragePort` lives), add a small hierarchy
next to the port, paralleling `IdentityError`:
- `StorageError(Exception)` — base.
- `StorageUnavailableError(StorageError)` — outage / provider 5xx / transport / bad key /
  misconfig (infrastructural; not the caller's fault).
- `StorageNotFoundError(StorageError)` — the requested object does not exist.

### 2. Infrastructure — adapter (`app/infrastructure/storage/supabase_adapter.py`)
- Wrap each blocking SDK call in `await asyncio.to_thread(<callable>, <args>)`.
- Add `_classify_storage(exc) -> StorageError`, paralleling identity's `_classify`:
  - storage3 `StorageApiError` whose status is 404 / message indicates "not found" →
    `StorageNotFoundError`;
  - `StorageApiError` 5xx, "api key"/auth-key failures, and any non-HTTP transport error
    (DNS/connection/TLS/timeout) → `StorageUnavailableError`;
  - anything else genuinely unexpected → re-raise as-is (stays a loud 500 — never silently
    downgraded), same philosophy as the identity classifier.
- Apply classification to **`upload` and `get_presigned_url`** (critical path — the client
  needs a truthful status): `try: await to_thread(...) except Exception as e: raise _classify_storage(e)`.
- **`delete` stays a best-effort `bool`** (swallow + log, only add the `to_thread` wrap): it
  is called *after* the DB commit as compensation, so it must never raise a 503 for an
  already-committed delete.
- Introduce `DEFAULT_PRESIGN_TTL = 3600` used as the `get_presigned_url` default.

### 3. HTTP layer — handlers + i18n (`app/core/exceptions.py`, `app/main.py`, `app/i18n/*.json`)
- `storage_unavailable_handler` → 503, `code = "storage_unavailable"`.
- `storage_not_found_handler` → 404, `code = "storage_not_found"`.
- Register both in `main.py` alongside `identity_unavailable_handler` (Starlette matches by
  MRO; register the subclasses).
- Add `error.storage_unavailable` and `error.storage_not_found` to all four locales
  (vi/en/zh/fr).

### 4. Small correctness fixes (same S1 area)
- **S1-4 presign expiry** (`document/handlers.py` upload): `presigned_url_expires_at` is
  currently `datetime.now(UTC)` (already-expired). Compute `now + DEFAULT_PRESIGN_TTL`.
- **S1-5 `set_avatar` ordering** (`document/handlers.py`): presign currently runs *before*
  the `emit_audit_event` commit, so a storage outage aborts a pure-DB avatar change. Reorder:
  commit first, then presign best-effort — on `StorageError` return `None` (the route already
  treats the URL as optional). A DB write must not be gated on a read-side storage call.
- **S1-7** remove dead `app/services/storage.py` (0 importers — grep-verified).

### 5. Tests (TDD)
- **Unit** `tests/unit/infrastructure/test_storage_error_classification.py` — pin the
  `_classify_storage` table (not-found→NotFound, 5xx/transport/bad-key→Unavailable,
  unexpected→re-raise), mirroring `test_identity_error_classification.py`.
- **HTTP/integration** — with the storage client stubbed to raise: `POST /documents` and
  `GET /documents/{id}` surface the **503 `storage_unavailable`** envelope; a not-found object
  on presign surfaces **404 `storage_not_found`**; assert the envelope shape matches the
  standard `{error:{code,message,detail}}`.
- **Expiry** — an upload response's `presigned_url_expires_at` is ≈ `now + DEFAULT_PRESIGN_TTL`,
  not `now`.
- **Happy path** — upload / delete / set_avatar still succeed; `set_avatar` returns a URL on
  success and does not roll back the avatar change when presign fails (returns `None`).
- Sabotage check: reverting the `to_thread` wrap must not break tests (behavioural parity),
  but the classification tests must fail if the `except → raise _classify` is removed.

## Out of scope (deliberate)
- Migrating to the Supabase async client (larger change; `to_thread` suffices).
- Constraint-name→friendly-code granularity in the generic IntegrityError handler (separate).
- The deferred low-frequency concurrency races (PR-G residual) and later PRs H/J/K.
- Storage-object garbage-collection / orphan sweeper (a future ops task; orphans are logged).

## Files touched
`app/domain/document/repository.py` · `app/infrastructure/storage/supabase_adapter.py` ·
`app/core/exceptions.py` · `app/main.py` · `app/application/document/handlers.py` ·
`app/i18n/{vi,en,zh,fr}.json` · delete `app/services/storage.py` · new + existing tests.

## Packaging
One PR `fix/storage-taxonomy-offload`, TDD → full gate (`scripts/check.sh`) → subagent review → PR.
