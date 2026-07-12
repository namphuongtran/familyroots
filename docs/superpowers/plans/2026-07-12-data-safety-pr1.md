# Data Safety PR1 Implementation Plan — Clan Export + Document Deletion Safety

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A clan admin can download a lossless JSON archive + GEDCOM of their gia phả, and deleting a document becomes recoverable (soft-delete + 30-day retention purge) instead of instant permanent loss.

**Architecture:** Spec = `docs/superpowers/specs/2026-07-12-data-safety-design.md` (PR1 scope). Export is pure read-side CQRS: a new export query port gathers raw dict rows, pure serializer modules (`clan_export.py`, `gedcom_export.py`) turn them into bytes, a thin admin-only route streams the file (envelope-exempt). Document deletion flips from hard-delete+blob-removal to soft-delete (migration 016 adds the columns that never existed) with a new restore endpoint and a daily advisory-locked purge job that removes blob+row after `DOCUMENT_RETENTION_DAYS`.

**Tech Stack:** Existing FastAPI/SQLAlchemy async/Alembic/pytest stack; serializers are pure stdlib (`json`, string building — NO new dependencies, GEDCOM is hand-rolled).

## Global Constraints

- Quality gate after EVERY task (from `backend/`): `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` (mypy MUST be `uv run mypy`, never `uvx mypy`).
- Migration id `016_document_soft_delete` revises `015_data_integrity`; single linear chain; ≤32 chars.
- No new dependencies; serializers import stdlib only.
- Handlers raise `app.domain.shared.exceptions.*` only; import-linter ratchet must not grow (application must not import app.core/app.models/app.infrastructure — the export handler depends on Protocol ports defined in domain/application, wired in `dependencies.py`).
- The export endpoint returns a FILE and is envelope-exempt (like `/health`) — every other endpoint keeps `{"data": ...}`.
- JSON export INCLUDES soft-deleted persons/marriages/parent_child rows flagged with `is_deleted` (archives keep history); GEDCOM EXCLUDES them; documents manifest includes only live (non-deleted) documents.
- No new i18n error codes (reuse `document_not_found`; validation via Pydantic patterns).
- Integration tests need Postgres: `docker compose up -d pgdb`. Never `git add -A`.

---

### Task 1: Migration 016 + document soft-delete columns

**Files:**
- Create: `backend/migrations/versions/016_document_soft_delete.py`
- Modify: `backend/app/models/document.py` (~line 39, next to `is_avatar`)
- Test: `backend/tests/integration/test_document_soft_delete_migration.py`

**Interfaces:**
- Produces: columns `documents.is_deleted BOOLEAN NOT NULL server_default 'false'`, `documents.deleted_at TIMESTAMPTZ NULL`, `documents.deleted_by UUID NULL`; partial index `idx_documents_is_deleted ON documents (is_deleted) WHERE is_deleted = false`; matching ORM `Mapped` columns. Tasks 2–3 rely on these exact names.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_document_soft_delete_migration.py
"""Migration 016: documents gain soft-delete columns (they never had them)."""

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.integration


def test_document_soft_delete_columns_exist(sync_engine):
    insp = sa.inspect(sync_engine)
    cols = {c["name"]: c for c in insp.get_columns("documents")}
    assert "is_deleted" in cols and cols["is_deleted"]["nullable"] is False
    assert "deleted_at" in cols and cols["deleted_at"]["nullable"] is True
    assert "deleted_by" in cols and cols["deleted_by"]["nullable"] is True


def test_partial_index_exists(sync_engine):
    with sync_engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT indexdef FROM pg_indexes WHERE indexname = 'idx_documents_is_deleted'")
        ).first()
    assert row is not None and "WHERE (is_deleted = false)" in row[0]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/integration/test_document_soft_delete_migration.py -q`
Expected: FAIL — `is_deleted` not in columns.

- [ ] **Step 3: Write the migration**

```python
# backend/migrations/versions/016_document_soft_delete.py
"""Documents move from hard-delete to soft-delete (ADR-019, data-safety PR1).

The entity's mark_deleted() existed but only emitted an event — the table never
had soft-delete columns and the repository issued a physical DELETE + permanent
blob removal. For irreplaceable scanned heritage documents that is data loss on
a misclick. These columns give documents the same recoverable-delete semantics
as persons; a retention purge job removes blob+row after DOCUMENT_RETENTION_DAYS.

Revision ID: 016_document_soft_delete
Revises: 015_data_integrity
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "016_document_soft_delete"
down_revision: str | None = "015_data_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("documents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "documents", sa.Column("deleted_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.execute(
        "CREATE INDEX idx_documents_is_deleted ON documents (is_deleted) WHERE is_deleted = false"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_documents_is_deleted")
    op.drop_column("documents", "deleted_by")
    op.drop_column("documents", "deleted_at")
    op.drop_column("documents", "is_deleted")
```

(Import style: check migration 015 for how it imports postgresql UUID — mirror it; `sa.dialects.postgresql` may need `from sqlalchemy.dialects import postgresql` + `postgresql.UUID(as_uuid=True)`.)

- [ ] **Step 4: Add ORM columns** in `backend/app/models/document.py` next to `is_avatar` (import `DateTime` if absent; UUID already imported):

```python
    # Soft delete (ADR-019): rows are recoverable until the retention purge job
    # removes blob + row after DOCUMENT_RETENTION_DAYS.
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
```

- [ ] **Step 5: Run tests + drift gate**

Run: `cd backend && uv run pytest tests/integration/test_document_soft_delete_migration.py tests/integration/test_schema_baseline.py -q`
Expected: PASS (round-trip + autogenerate-no-diff).

- [ ] **Step 6: Full gate, commit**

```bash
git add backend/migrations/versions/016_document_soft_delete.py backend/app/models/document.py backend/tests/integration/test_document_soft_delete_migration.py
git commit -m "feat(backend): migration 016 — document soft-delete columns (data-safety)"
```

---

### Task 2: Document soft-delete behavior + restore endpoint

**Files:**
- Modify: `backend/app/domain/document/entity.py` (soft-delete state on the dataclass; `mark_deleted` sets it; new `restore(actor)`; new event)
- Modify: `backend/app/domain/document/events.py` (add `DocumentRestored`)
- Modify: `backend/app/infrastructure/persistence/document_repository.py` (`delete()` → soft; reads filter; new `get_deleted`; mapper carries the 3 fields — check `document_mapper` or inline `to_orm`/`apply_to_orm` in the repository file, follow where they live)
- Modify: `backend/app/application/document/handlers.py:146-167` (`delete` no longer touches storage; new `restore`)
- Modify: `backend/app/api/v1/documents.py` (new `POST /{document_id}/restore`, RequireAdmin)
- Modify: `backend/docs update deferred to Task 6`
- Test: `backend/tests/integration/test_document_soft_delete.py` (+ update existing delete tests — grep `documents` under backend/tests for DELETE flows)

**Interfaces:**
- Consumes: Task 1 columns.
- Produces: `DocumentCommandHandler.delete(...)` (same signature) now soft-deletes and does NOT call storage; `DocumentCommandHandler.restore(*, document_id, clan_id, actor) -> DocumentResponse`; repo `delete(doc)` performs UPDATE; repo `get_by_id`/`list_in_clan`/`get_person_avatars` exclude `is_deleted=true`; repo `get_deleted(document_id, clan_id)` for the restore path. Task 3 relies on the columns + `storage_path` to purge.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integration/test_document_soft_delete.py
"""ADR-019: document delete is recoverable — blob survives, restore works."""

import pytest

pytestmark = pytest.mark.integration

# Fixtures: seed clan + admin/editor auth + one uploaded document via the API
# (multipart POST /api/v1/documents with a small PNG payload) — mirror the
# existing document upload tests' fixture style (grep tests for "documents").


async def test_delete_soft_deletes_and_keeps_blob(client, admin_headers, uploaded_document):
    doc_id, storage_path = uploaded_document
    resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert resp.status_code == 200  # existing message-envelope shape unchanged
    # gone from the list and from GET
    listing = await client.get("/api/v1/documents", headers=admin_headers)
    assert all(d["id"] != str(doc_id) for d in listing.json()["data"])
    get_resp = await client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert get_resp.status_code == 404
    # but the row is flagged, not gone, and the blob was NOT deleted
    # (assert via raw SQL: is_deleted=true, deleted_at set; and storage.delete was
    # never called — monkeypatch/spy the storage adapter delete in this test)


async def test_restore_brings_document_back(client, admin_headers, uploaded_document):
    doc_id, _ = uploaded_document
    await client.delete(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    resp = await client.post(f"/api/v1/documents/{doc_id}/restore", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == str(doc_id)
    get_resp = await client.get(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert get_resp.status_code == 200  # presigned URL flows again


async def test_restore_requires_admin_and_404s(client, editor_headers, admin_headers, uploaded_document):
    doc_id, _ = uploaded_document
    await client.delete(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert (await client.post(f"/api/v1/documents/{doc_id}/restore", headers=editor_headers)).status_code == 403
    ok = await client.post(f"/api/v1/documents/{doc_id}/restore", headers=admin_headers)
    assert ok.status_code == 200
    again = await client.post(f"/api/v1/documents/{doc_id}/restore", headers=admin_headers)
    assert again.status_code == 404  # not-deleted → restore has nothing to do
```

Fill in the raw-SQL assertions and the storage-delete spy concretely (patch where the handler imports its storage port instance — read `dependencies.py` wiring for documents first).

- [ ] **Step 2: Run to verify failure** — delete currently HARD-deletes (raw-SQL row check fails) and `/restore` is 404/405. Expected: FAIL.
- [ ] **Step 3: Implement**

`entity.py` — replace the event-only `mark_deleted` and add state + restore:

```python
    # Soft delete (ADR-019)
    is_deleted: bool = False
    deleted_at: datetime | None = None
    deleted_by: uuid.UUID | None = None

    def mark_deleted(self, actor: ActorInfo) -> None:
        """Soft-delete: the repository persists this state; the blob stays until
        the retention purge job (ADR-019)."""
        self.is_deleted = True
        self.deleted_at = datetime.now(UTC)
        self.deleted_by = actor.user_id
        self.add_event(DocumentDeleted(  # keep the EXISTING call's fields exactly as they are today
            document_id=self.id, clan_id=self.clan_id,
            actor_id=actor.user_id, actor_role=actor.role,
        ))

    def restore(self, actor: ActorInfo) -> None:
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.add_event(
            DocumentRestored(
                document_id=self.id, clan_id=self.clan_id,
                actor_id=actor.user_id, actor_role=actor.role,
            )
        )
```

`events.py` — `DocumentRestored(AuditableEvent)` mirroring `DocumentDeleted` (action stamped by the base-class convention — copy `DocumentDeleted`'s shape exactly).

`document_repository.py` — `delete()` becomes a save of the mutated state (UPDATE, not `session.delete`); add `is_deleted == False` filters to `get_by_id`, `list_in_clan`, `get_person_avatars`; new `get_deleted(document_id, clan_id)` returning only a soft-deleted row; ensure the mapper/`apply_to_orm` carries the 3 new fields.

`handlers.py::delete` — drop the storage call + orphan log entirely:

```python
        doc = await self._get_or_raise(document_id, clan_id)
        doc.mark_deleted(actor)
        await self._repo.save(doc)
        await self._uow.commit()
```

New `handlers.py::restore` — `get_deleted` or raise `EntityNotFoundError("document_not_found")`; `doc.restore(actor)`; save; commit; return the same response model `get` uses.

Route — mirror the persons restore route shape (`persons.py:407`), `RequireAdmin`, returns `{"data": ...}`.

- [ ] **Step 4: Run new tests + ALL existing document tests** (grep and run every test file touching documents). Update existing delete-flow tests to the new semantics (they may assert the row is gone or storage.delete called — flip to soft-delete expectations; do NOT delete assertions, re-point them).
- [ ] **Step 5: Full gate, commit**

```bash
git add backend/app backend/tests
git commit -m "feat(backend): document delete is soft + restorable; blob survives until purge (ADR-019)"
```

---

### Task 3: Retention purge job

**Files:**
- Modify: `backend/app/core/config.py` (add `DOCUMENT_RETENTION_DAYS: int = 30`)
- Create: `backend/app/services/document_purge.py`
- Modify: `backend/app/services/scheduler.py:25-42` (`start_scheduler` registers the purge job)
- Test: `backend/tests/integration/test_document_purge_job.py`

**Interfaces:**
- Consumes: Task 1 columns; the storage adapter's `delete(storage_path) -> bool`; the advisory-lock pattern from `scheduler.py` (`pg_try_advisory_lock`, dedicated connection, rollback-before-unlock).
- Produces: `async def purge_expired_documents(now: datetime | None = None) -> None` in `app/services/document_purge.py`; own lock key `_PURGE_LOCK_KEY = 728_115_002`; cron registered daily at `CronTrigger(hour=settings.NOTIFICATION_CRON_HOUR, minute=30, timezone=_TZ)` with id `document_purge`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integration/test_document_purge_job.py
"""ADR-019 purge: soft-deleted documents past retention lose blob + row;
fresh deletions and live documents are untouched; failures are isolated."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.integration

# Fixture style: mirror tests/integration/test_lunar_anniversary_job.py
# (monkeypatch app engine/sessionmaker to the migrated DB, seed via raw SQL).
# Seed three soft-deleted documents by raw SQL with deleted_at = now-40d,
# now-40d (poison path), now-1d, plus one live document. Storage adapter's
# delete is monkeypatched with a spy that raises for the poison path.


# Four tests — write each fully, using the seeded ids from the fixture above:
#
# test_purge_removes_expired_keeps_fresh_and_live:
#   await purge_expired_documents()
#   assert expired doc's storage_path in the storage spy's calls
#   raw SQL: expired doc row count == 0; fresh-deleted doc row count == 1 with
#   is_deleted true; live doc row count == 1 with is_deleted false
#
# test_purge_isolates_per_item_failures:
#   storage spy raises RuntimeError ONLY for the poison doc's path
#   await purge_expired_documents()
#   raw SQL: poison doc row SURVIVES (retry next run); the other expired doc
#   is gone in the same run
#
# test_purge_second_run_idempotent:
#   await purge_expired_documents(); await purge_expired_documents()
#   second run: storage spy call count unchanged from first run; no exception
#
# test_missing_blob_still_purges_row:
#   storage spy returns False (blob already absent) for the expired doc
#   await purge_expired_documents()
#   raw SQL: row purged anyway
```

The lunar job test file (`tests/integration/test_lunar_anniversary_job.py`) is the template for engine/session monkeypatching and advisory-lock-safe invocation; the storage spy is a monkeypatch of `app.services.document_purge.SupabaseStorageAdapter` (patch at the purge module's import seam).

- [ ] **Step 2: Run to verify failure** — module doesn't exist. Expected: FAIL (import error).
- [ ] **Step 3: Implement `document_purge.py`** — structure copied from `send_anniversary_notifications`:

```python
"""Retention purge for soft-deleted documents (ADR-019).

Daily job: documents with is_deleted = true AND deleted_at older than
DOCUMENT_RETENTION_DAYS lose their storage blob, then their row — in that
order (a failed blob delete leaves the row for the next run; the reverse
would orphan blobs). Per-item isolation: one failure never stops the sweep.
Advisory-locked on its own key so multi-replica deployments run it once.
"""

_PURGE_LOCK_KEY = 728_115_002

async def purge_expired_documents(now: datetime | None = None) -> None:
    from app.core.database import engine
    from app.infrastructure.storage.supabase_adapter import SupabaseStorageAdapter

    if now is None:
        now = datetime.now(UTC)
    cutoff = now - timedelta(days=settings.DOCUMENT_RETENTION_DAYS)
    storage = SupabaseStorageAdapter()

    async with engine.connect() as conn:
        acquired = await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _PURGE_LOCK_KEY})
        if not acquired.scalar():
            logger.info("Document purge lock held elsewhere — skipping")
            await conn.rollback()
            return
        await conn.commit()
        db = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            rows = (await db.execute(
                text("""SELECT id, storage_path FROM public.documents
                        WHERE is_deleted = true AND deleted_at < :cutoff"""),
                {"cutoff": cutoff},
            )).mappings().all()
            for row in rows:
                try:
                    await storage.delete(row["storage_path"])  # False (missing) is fine
                    await db.execute(text("DELETE FROM public.documents WHERE id = :id"), {"id": row["id"]})
                    await db.commit()
                    logger.info("Purged expired document %s", row["id"])
                except Exception:
                    logger.exception("Purge failed for document %s — will retry next run", row["id"])
                    await db.rollback()
                    continue
        finally:
            await db.rollback()
            await db.close()
            await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _PURGE_LOCK_KEY})
            await conn.commit()
```

(Check how the storage adapter is normally constructed/injected — if `dependencies.py` builds it with arguments, mirror that; a `StorageError` subclass may wrap failures — catching broad `Exception` per item is intentional here.) Register in `start_scheduler` after the anniversary job:

```python
    scheduler.add_job(
        func=purge_expired_documents,
        trigger=CronTrigger(hour=settings.NOTIFICATION_CRON_HOUR, minute=30, timezone=_TZ),
        id="document_purge",
        replace_existing=True,
        misfire_grace_time=3600,
    )
```

- [ ] **Step 4: Run tests** — all four pass; also rerun scheduler tests (`tests/integration/test_scheduler_lock.py` etc.) for regression.
- [ ] **Step 5: Full gate, commit**

```bash
git add backend/app/services/document_purge.py backend/app/services/scheduler.py backend/app/core/config.py backend/tests/integration/test_document_purge_job.py
git commit -m "feat(backend): daily retention purge job for soft-deleted documents (ADR-019)"
```

---

### Task 4: Clan export — query port, JSON archive, endpoint

**Files:**
- Create: `backend/app/application/export/__init__.py`, `backend/app/application/export/handlers.py`
- Create: `backend/app/application/export/ports.py` (Protocol for the query port + the storage-presign seam)
- Create: `backend/app/infrastructure/persistence/export_query_port.py`
- Create: `backend/app/services/clan_export.py`
- Create: `backend/app/api/v1/exports.py`; Modify: `backend/app/api/v1/router.py` (include with `prefix="/exports", tags=["exports"]`); Modify: `backend/app/infrastructure/dependencies.py` (provider `get_export_query_handler`)
- Test: `backend/tests/integration/test_clan_export_json.py`, `backend/tests/unit/test_clan_export_serializer.py`

**Interfaces:**
- Consumes: SQL function `public.get_family_tree_flat(root, clan, depth)` (returns person_id + depth; used for the đời map); storage `get_presigned_url(storage_path, expires_in)` (read the adapter for the exact signature); founder = `clan_memberships.is_founder = true`.
- Produces (Task 5 + 6 rely on these EXACT names):
  - `ExportQueryPort` Protocol in `app/application/export/ports.py` with: `clan(clan_id) -> dict`, `persons(clan_id) -> list[dict]` (JOIN memberships; INCLUDES soft-deleted persons; row carries membership fields `membership_role/stored_generation/is_founder/branch_id`), `branches(clan_id) -> list[dict]`, `marriages(clan_id) -> list[dict]` (incl. soft-deleted), `parent_child(clan_id) -> list[dict]` (incl. soft-deleted), `events(clan_id) -> list[dict]`, `documents(clan_id) -> list[dict]` (live only), `generation_map(clan_id) -> dict[uuid.UUID, int]` (per founder: `SELECT person_id, depth FROM public.get_family_tree_flat(:founder, :clan, 50)` → `depth + 1`, first founder wins).
  - `build_clan_export(...) -> dict` and `to_json_bytes(payload: dict) -> bytes` in `app/services/clan_export.py` (pure; `json.dumps(..., ensure_ascii=False, indent=2, default=str)`).
  - `ExportQueryHandler.export_clan(clan_id, fmt: str) -> tuple[str, str, bytes]` (filename, media_type, body). For `fmt="json"`: media type `application/json`.
  - Route `GET /api/v1/exports/clan?format=json|gedcom` — `format: str = Query("json", pattern="^(json|gedcom)$")`, RequireAdmin, returns `fastapi.Response(content=body, media_type=..., headers={"Content-Disposition": f'attachment; filename="{filename}"'})`.

- [ ] **Step 1: Write the failing integration test** — build THE rich fixture (this is the heart of the PR's test value; raw-SQL seeding, mirror the style of `tests/integration/test_relationship_update_validation.py` fixtures):

```python
# backend/tests/integration/test_clan_export_json.py
"""Lossless JSON archive: everything a clan needs to survive outside the SaaS."""
# Fixture "clan đủ gia vị":
#   thủy tổ (is_founder=true, đời 1, birth 1920-01-01 precision=year, lunar_birth "15/08 Canh Thân")
#   ├── con trưởng (đời 2, vợ cả spouse_order=1, vợ hai spouse_order=2 — đa thê)
#   │     ├── cháu A (đời 3, mẹ = vợ cả, birth precision=circa display "khoảng 1975")
#   │     └── cháu B (đời 3, relationship_type='adopted')
#   ├── một person soft-deleted (is_deleted=true)
#   một marriage soft-deleted; một branch "Chi Hai"; một event giỗ lunar recurring;
#   một document live (uploaded via API for a real storage path) — plus admin/editor
#   users for two clans (clan B seeded minimal for the isolation test).

async def test_json_export_contains_everything(client, admin_headers, rich_clan):
    resp = await client.get("/api/v1/exports/clan?format=json", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert 'attachment; filename="' in resp.headers["content-disposition"]
    data = resp.json()  # the archive itself, NOT {"data": ...} — envelope-exempt
    assert data["format"] == "familyroots-clan-export" and data["format_version"] == 1
    persons = {p["full_name"]: p for p in data["persons"]}
    assert persons["Cụ Thủy Tổ"]["generation"] == 1
    assert persons["Cháu A"]["generation"] == 3
    assert persons["Cháu A"]["birth_date_precision"] == "circa"
    assert persons["Cháu A"]["birth_date_display"] == "khoảng 1975"
    assert persons["Cụ Thủy Tổ"]["lunar_birth_date"] == "15/08 Canh Thân"
    deleted = [p for p in data["persons"] if p["is_deleted"]]
    assert len(deleted) == 1  # archive keeps history, flagged
    orders = sorted(m["spouse_order"] for m in data["marriages"] if m["spouse_order"] and not m["is_deleted"])
    assert orders == [1, 2]
    assert any(pc["relationship_type"] == "adopted" for pc in data["parent_child"])
    assert any(m["is_deleted"] for m in data["marriages"])
    assert any(e["is_lunar_calendar"] for e in data["events"])
    assert data["branches"][0]["name"] == "Chi Hai"
    manifest = data["documents_manifest"]
    assert len(manifest) == 1 and manifest[0]["download_url"].startswith("http")


async def test_export_isolation_two_sided(client, admin_headers, clan_b_admin_headers, rich_clan):
    a = (await client.get("/api/v1/exports/clan?format=json", headers=admin_headers)).json()
    b = (await client.get("/api/v1/exports/clan?format=json", headers=clan_b_admin_headers)).json()
    a_ids = {p["id"] for p in a["persons"]}
    b_ids = {p["id"] for p in b["persons"]}
    assert a_ids and not (a_ids & b_ids)


async def test_export_requires_admin(client, editor_headers, rich_clan):
    resp = await client.get("/api/v1/exports/clan?format=json", headers=editor_headers)
    assert resp.status_code == 403


async def test_export_invalid_format_422(client, admin_headers, rich_clan):
    resp = await client.get("/api/v1/exports/clan?format=xml", headers=admin_headers)
    assert resp.status_code == 422
```

Plus `tests/unit/test_clan_export_serializer.py`: `build_clan_export` is pure — given hand-built row dicts, output has the exact top-level keys `{"format","format_version","exported_at","clan","persons","clan_memberships","branches","marriages","parent_child","events","documents_manifest"}`; `to_json_bytes` round-trips through `json.loads`; UUID/date/datetime values serialize via `default=str`.

- [ ] **Step 2: Run to verify failure** — 404 on the route. Expected: FAIL.
- [ ] **Step 3: Implement** per the Interfaces block. Key specifics:
  - Port SQL: plain `text()` selects of ALL business columns (`SELECT * FROM` is acceptable here — this is an archival dump; convert RowMapping → dict). Persons query: `SELECT p.*, cm.role AS membership_role, cm.generation AS stored_generation, cm.is_founder, cm.branch_id FROM persons p JOIN clan_memberships cm ON cm.person_id = p.id WHERE cm.clan_id = :clan` (NO is_deleted filter). Edges: `WHERE created_by_clan_id = :clan` (no filter). Events/branches: `WHERE clan_id = :clan`. Documents: `WHERE clan_id = :clan AND is_deleted = false`.
  - `generation_map`: founders from memberships; for each, run the tree SQL function; `dict.setdefault(person_id, depth + 1)`.
  - Handler assembles: presigns each manifest row (`download_url`, `download_url_expires_at` = now + TTL; use the adapter's existing default TTL constant), stamps `exported_at` with `ZoneInfo(settings.SCHEDULER_TIMEZONE)`... **careful**: application layer must not import `app.core.config` (ratchet). Thread the timezone/UTC decision the simple way: `exported_at = datetime.now(UTC).isoformat()` (archival timestamps in UTC are unambiguous — document in the contract). Filename: `f"{clan['slug']}-gia-pha-{date.today().isoformat()}.json"`.
  - `persons` rows get `generation` injected from the map (`None` when absent) — the serializer does this merge (pure), not the port.
  - Wire `get_export_query_handler` in `dependencies.py` (port over bare session + the storage adapter instance — mirror how document handlers get their storage).
- [ ] **Step 4: Run tests until green; run the full suite** (existing tests must be untouched).
- [ ] **Step 5: Full gate, commit**

```bash
git add backend/app backend/tests
git commit -m "feat(backend): clan export — lossless JSON archive endpoint (admin, envelope-exempt)"
```

---

### Task 5: GEDCOM 5.5.1 export

**Files:**
- Create: `backend/app/services/gedcom_export.py`
- Modify: `backend/app/application/export/handlers.py` (`fmt="gedcom"` branch → media type `text/x-gedcom`, filename `.ged`)
- Test: `backend/tests/unit/test_gedcom_export.py`, `backend/tests/integration/test_clan_export_gedcom.py`

**Interfaces:**
- Consumes: the same port row dicts + `generation_map` from Task 4 (exact keys as Task 4's port produces).
- Produces: `build_gedcom(clan: dict, persons: list[dict], marriages: list[dict], parent_child: list[dict], branches: list[dict], generation_map: dict) -> str` in `app/services/gedcom_export.py` (pure stdlib).

- [ ] **Step 1: Write the failing unit tests** — cover the mapping table explicitly:

```python
# backend/tests/unit/test_gedcom_export.py  (hand-built row dicts, no DB)
- header/trailer: starts "0 HEAD", contains "1 GEDC"/"2 VERS 5.5.1"/"1 CHAR UTF-8"/"1 SOUR FamilyRoots", ends "0 TRLR"
- one INDI per NON-deleted person; soft-deleted persons ABSENT (is_deleted rows dropped)
- NAME from full_name; SEX M/F/U from gender male/female/unknown
- dates by precision: exact 1975-03-10 → "2 DATE 10 MAR 1975"; year → "2 DATE 1975";
  month → "2 DATE MAR 1975"; circa → "2 DATE ABT 1975" (year-level ABT); unknown → no DATE line
- Vietnamese NOTE: person with posthumous_name/birth_name/lunar/generation/branch →
  one "1 NOTE FamilyRoots: ten_huy=...; ten_thuy=...; doi=3; chi=Chi Hai; lunar_birth=..."
- FAM per non-deleted marriage: HUSB/WIFE by gender (fallback person1→HUSB);
  divorced → "1 DIV"; "1 NOTE spouse_order=2; status=married" when set
- child linking: child with father+mother married → CHIL in that FAM + FAMC on child;
  single-parent edge → its own FAM with one parent; adopted → "2 PEDI adopted" under FAMC
- xref integrity: every @I..@/@F..@ referenced exists; deterministic numbering (sorted by id)
- CONC/line length: lines never exceed 255 chars (long biography NOTE folds with CONC)
```

Write each as a real test with small fixture dicts (5–8 tests). Integration test (`test_clan_export_gedcom.py`): reuse Task 4's rich-clan fixture pattern; GET `?format=gedcom` → 200, content-disposition `.ged`, response text contains `0 HEAD`, exactly N `0 @I` records (live persons only), the ABT date, and a NOTE carrying `doi=`; two-sided isolation piggybacks on Task 4's test (no need to repeat).

- [ ] **Step 2: Run to verify failure** — module missing. Expected: FAIL.
- [ ] **Step 3: Implement** `build_gedcom` per the tested mapping: build xref maps (`person_id → @I{n}@` sorted by uuid for determinism), emit INDI blocks, group parent_child by (father, mother) pairs matched against marriages for FAM assembly, single-parent FAMs for unmatched edges, fold long NOTEs with `CONC` at 240 chars. Wire the handler branch.
- [ ] **Step 4: Run unit + integration tests + full suite.**
- [ ] **Step 5: Full gate, commit**

```bash
git add backend/app/services/gedcom_export.py backend/app/application/export/handlers.py backend/tests
git commit -m "feat(backend): GEDCOM 5.5.1 clan export (VN concepts preserved in NOTE)"
```

---

### Task 6: Docs — ADR-019/020, contracts, ops rows

**Files:**
- Create: `docs/decisions/019-document-soft-delete-purge.md`, `docs/decisions/020-clan-export-formats.md`
- Create: `docs/contracts/rest-exports-api.md`
- Modify: `docs/decisions/README.md` (rows 019, 020); `docs/decisions/006-soft-vs-hard-delete.md` (Status note: documents row superseded by 019)
- Modify: `docs/contracts/rest-documents-api.md` (delete-is-soft + restore endpoint + retention); `docs/contracts/README.md` (exports entry + envelope-exemption note); `docs/architecture/api-design.md` (Exports section + documents restore row); `docs/architecture/data-model.md` (documents soft-delete columns); `docs/architecture/storage.md` (delete semantics + purge job — replace the ⚠️ hard-delete banner); `docs/ops/configuration.md` (`DOCUMENT_RETENTION_DAYS` row); `docs/architecture/notifications-scheduler.md` (second job: document_purge, lock key, schedule)
- Test: none — full gate as evidence.

**Interfaces:** Documents what Tasks 1–5 shipped; every claim verified against code first.

- [ ] **Step 1: ADR-019** (house style of 017/018): documents hard-delete → soft-delete + `DOCUMENT_RETENTION_DAYS` purge; blob outlives the row-delete; restore endpoint; supersedes ADR-006's documents row; orphan-blob reconciliation deferred (bucket listing pagination) — follow-up ticket; avatar-of-deleted-document keeps working until purge (accepted).
- [ ] **Step 2: ADR-020**: lossless JSON archive (versioned schema, includes flagged soft-deleted rows, UTC timestamps, manifest-not-blobs) + GEDCOM 5.5.1 interop view (excludes deleted; VN concepts in structured NOTE); sync admin-only download; import-from-JSON deliberately enabled-by-design but out of scope; PDF book deferred.
- [ ] **Step 3: rest-exports-api.md** — house contract style: endpoint, params, roles, **envelope-exempt** (returns the file itself), filename convention, JSON schema outline + PII note (phone/email included — admin export of the clan's own data), GEDCOM mapping table (the same table the unit tests pin), stability rule: `format_version` bumps on breaking archive changes.
- [ ] **Step 4: remaining doc edits** per Files list; verify each against shipped code.
- [ ] **Step 5: Full gate one final time; commit**

```bash
git add docs
git commit -m "docs: ADR-019/020 + exports contract + document soft-delete doc sweep"
```
