# Transaction & Pool Hygiene (A6 / H5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** No external Supabase call runs while a pooled DB connection is checked out (upload + export), and the pool is env-tunable — closing review finding H5, the last High. Spec: `docs/superpowers/specs/2026-07-18-txn-pool-hygiene-design.md`.

**Architecture (ADR-028):** upload does validate → `uow.rollback()` (release the read txn) → blob upload (no connection held) → fresh write txn; export reads everything → `port.release()` → presign with no connection held; `create_async_engine` reads `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` from Settings via a `make_engine(settings)` factory. No migration; no contract/error-code change.

**Tech Stack:** SQLAlchemy async (`AsyncSession.in_transaction()` is the test oracle), pydantic-settings, real-PG integration tests with a session-transaction-recording storage double.

## Global Constraints

- **The invariant:** at the moment ANY `self._storage.*` network call (`upload`, `get_presigned_url`) runs in the upload/export paths, `session.in_transaction()` must be **False**. This is the acceptance oracle — deterministic, no timing.
- Validate-before-upload preserved: a bad/foreign/soft-deleted `person_id` → 404 `person_not_found` with `storage.upload` **never called**.
- Existing orphan-blob compensation (delete-on-save-failure) unchanged; existing document/export API contracts, response shapes, error codes unchanged.
- Pool defaults stay 10 + 20 (no out-of-box behavior change); only tunability + docs are added.
- Background jobs' dedicated `engine.connect()` model unchanged (documented in headroom math).
- RED-first; full gate before done: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.

---

### Task 1: RED — the "no connection held during external I/O" invariant + tunability

**Files:**
- Create: `backend/tests/integration/test_txn_pool_hygiene.py`

**Interfaces:**
- Consumes: `migrated_db_url`; `DocumentCommandHandler` + `ExportQueryHandler` wiring (mirror `tests/integration/test_clan_export_json.py`'s DI, which already builds both over a real session with a FakeStorage). Note: `SqlAlchemyUnitOfWork.session` exposes the underlying `AsyncSession` for `.in_transaction()` inspection.

- [ ] **Step 1: Write the tests.** A recording storage double whose every method captures `session.in_transaction()` at call time:

```python
class TxnRecordingStorage:
    """StoragePort double that records the request session's transaction state
    at the instant each network call is made. in_transaction() is True iff a
    pooled connection is checked out in a live txn — so a recorded True means an
    external call ran while holding a connection (the H5 defect)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.upload_in_txn: list[bool] = []
        self.presign_in_txn: list[bool] = []
        self.uploaded: list[str] = []

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        self.upload_in_txn.append(self._session.in_transaction())
        self.uploaded.append(path)
        return path

    async def delete(self, storage_path: str) -> bool:
        return True

    async def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        self.presign_in_txn.append(self._session.in_transaction())
        return f"https://signed.example/{storage_path}"
```

Tests (build the handler with the SAME session object the storage double inspects — construct `SqlAlchemyUnitOfWork(session, dispatcher)`, `TxnRecordingStorage(session)`, repo over `uow.session`):

```python
async def test_upload_holds_no_connection_during_blob_upload(...):
    # seed clan + live person; upload a doc with person_id set.
    # assert storage.upload_in_txn == [False]  (RED today: [True])
    # assert storage.presign_in_txn == [False]  (post-commit; likely already False)

async def test_upload_validates_before_uploading(...):
    # person_id = soft-deleted (or foreign) → EntityNotFoundError person_not_found
    # AND storage.uploaded == []  (validate-before-upload preserved; no wasted blob)

async def test_upload_happy_path_persists_and_returns_presigned(...):
    # live person → doc row committed, presigned url returned (correctness intact)

async def test_export_holds_no_connection_during_presign(...):
    # seed clan with >=2 documents; export_clan(fmt="json").
    # assert storage.presign_in_txn == [False, False]  (RED today: [True, True])
    # assert the archive still contains both documents (content unchanged)

def test_pool_settings_are_env_tunable():
    # make_engine(Settings(DB_POOL_SIZE=7, DB_MAX_OVERFLOW=3, DATABASE_URL=...))
    # assert engine.pool.size() == 7 and engine.pool._max_overflow == 3
    # (pure, no DB connection needed — QueuePool exposes .size()/_max_overflow)
```

If the export path can't expose the same session to the double (DI builds the port over its own session), construct the export handler explicitly in the test over a known session (as test_clan_export_json does) so the double inspects the real one — state how in the report.

- [ ] **Step 2: Run — record RED.** `uv run pytest tests/integration/test_txn_pool_hygiene.py -v`. Expected: `test_upload_holds_no_connection...` FAILS (`upload_in_txn == [True]`); `test_export_holds_no_connection...` FAILS (`[True, True]`); `test_pool_settings_are_env_tunable` FAILS (make_engine/settings don't exist yet); the two correctness tests PASS. Record exact values.
- [ ] **Step 3: Commit** — `git commit -m "test: RED — upload/export hold a DB connection during Supabase calls; pool not tunable (H5)"`.

---

### Task 2: The fixes

**Files:**
- Modify: `backend/app/application/document/handlers.py` (`upload` — release read txn before blob upload; audit `set_avatar`/`restore`)
- Modify: `backend/app/application/export/handlers.py` (`export_clan` — release before presign)
- Modify: `backend/app/application/export/ports.py` (add `release`) + `backend/app/infrastructure/persistence/export_query_port.py` (impl)
- Modify: `backend/app/core/config.py` (`DB_POOL_SIZE`/`DB_MAX_OVERFLOW`)
- Modify: `backend/app/core/database.py` (`make_engine(settings)` factory)

- [ ] **Step 1: Upload** — in `DocumentCommandHandler.upload`, immediately after the `person_in_clan` validation block and before building/uploading:

```python
        # ADR-028: end the read transaction so the multi-second Supabase blob
        # upload below holds NO pooled connection (H5). A None person_id skips
        # the read above; rollback() is then a no-op. The read has nothing to
        # persist, so rollback (not commit) is the cheap way to release.
        await self._uow.rollback()
```

Everything else in `upload` is unchanged (the blob upload, the save+commit write txn, the compensation, the post-commit presign). Verify: `person_in_clan`'s result is captured before the rollback (it is — it's checked inline). Do NOT change `set_avatar`/`restore` unless the Task-1 invariant test flags a storage call there running in-txn; the post-commit `get_presigned_url` calls (lines ~178, ~260) are already post-commit (no connection) — confirm via the invariant oracle if you extend the test, else leave them.

- [ ] **Step 2: Export release** — add to `ExportQueryPort` (ports.py):

```python
    async def release(self) -> None:
        """End the read transaction, returning the pooled connection (ADR-028)
        — called after all reads, before presigning, so N presign round-trips
        hold no connection."""
        ...
```

impl (export_query_port.py): `await self._session.rollback()` (read-only session → rollback releases the connection cleanly). In `export_clan`, in the JSON branch, after `documents = await self._port.documents(clan_id)` and before `_presign_manifest`:

```python
        await self._port.release()   # ADR-028: no connection held during presign
        documents_manifest = await self._presign_manifest(documents, now)
```

(The gedcom branch has no presign and returns earlier — release there is optional/harmless; add it before the gedcom return too for uniformity if trivial, else JSON-only with a comment.)

- [ ] **Step 3: Pool tunable** — `config.py` Settings: `DB_POOL_SIZE: int = 10`, `DB_MAX_OVERFLOW: int = 20`. `database.py`:

```python
def make_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=300,
        pool_pre_ping=True,
        echo=settings.APP_DEBUG,
    )

engine = make_engine(settings)
```

(Keep the module-level `engine`/`AsyncSessionLocal`/`get_db` exactly as-is otherwise; just source it from the factory.)

- [ ] **Step 4: Run.** Task-1 file all green ×2; then `uv run pytest tests/integration/test_clan_export_json.py tests/integration/test_document_soft_delete.py tests/integration -q -k "document or export or upload"`; then FULL suite (report count). If a test asserted the old in-txn behavior, none should — but if the export release surfaces a session-reuse issue (e.g., a later read after release), fix by ordering reads before release (all reads already precede presign). mypy: `make_engine` return type `AsyncEngine` (import from sqlalchemy.ext.asyncio).
- [ ] **Step 5: Commit** — `git commit -m "fix: release the pooled connection across Supabase upload/export calls; env-tunable pool (H5, ADR-028)"`.

---

### Task 3: ADR-028 + docs (grep-verified)

**Files:**
- Create: `docs/decisions/028-no-external-io-holding-db-connection.md`
- Modify: `docs/decisions/README.md` (028 row)
- Modify: `docs/ops/configuration.md` (DB_POOL_SIZE/DB_MAX_OVERFLOW + headroom math)
- Modify: `infra/render/render.yaml` (document the optional pool knobs as comments / non-secret env)
- Possibly: `docs/architecture/*` per grep

- [ ] **Step 1: ADR-028** (format of ADR-027): Context = H5 (upload read-txn held through blob upload; serial export presigns holding the session; hardcoded pool vs Supabase ceiling; `/health` starvation). Decision = no external network I/O while holding a pooled connection (release across Supabase calls via `uow.rollback()` / `port.release()`); pool env-tunable with headroom math. Consequences = uploads/exports no longer starve the pool; `/health` + the A1 logout/PATCH-me chokepoint pressure relieved; validate-before-upload preserved; defaults unchanged; per-request one extra txn boundary (negligible). Alternatives rejected = upload-first + compensate (wastes an upload on bad ids); a global connection semaphore (blunt); raising the pool without releasing (doesn't fix idle-in-transaction).
- [ ] **Step 2: configuration.md** — document `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`, defaults, and the headroom formula: `(pool_size + max_overflow + N_background_jobs) × instances ≤ provider connection ceiling`; note the two jobs (scheduler, purge) each take one dedicated connection.
- [ ] **Step 3: render.yaml** — add the two knobs as documented optional envs (with the default values in a comment; not `sync:false` — they're not secrets).
- [ ] **Step 4: Grep sweep** — `grep -rn "pool_size\|max_overflow\|idle-in-transaction\|presign\|pool" docs/contracts docs/architecture docs/ops --include='*.md' | grep -v "review-2026-07-18\|superpowers"`; disposition each; update any stale "hardcoded pool"/connection statement. Commit — `git commit -m "docs: ADR-028 no external I/O holding a DB connection + tunable pool headroom"`.

---

### Task 4: Full gate + verification (controller-run)

- [ ] `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` — all five green.
- [ ] Confirm Task-1 RED record showed `upload_in_txn == [True]` / export `[True, True]` before the fix (the negative control for the whole change).
