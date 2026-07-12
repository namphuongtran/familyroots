"""ADR-019 purge: soft-deleted documents past retention lose blob + row;
fresh deletions and live documents are untouched; failures are isolated.

Fixture style mirrors tests/integration/test_lunar_anniversary_job.py: monkeypatch
app.core.database.engine to the migrated throwaway DB, seed via raw SQL. The storage
adapter's delete() is monkeypatched at the purge module's import seam
(app.services.document_purge.SupabaseStorageAdapter) with a spy that records calls
and can be told to raise/return-False per path.
"""

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.database  # noqa: F401 — imported early so _reset_settings can't rebind it
from app.services.document_purge import purge_expired_documents

pytestmark = pytest.mark.integration


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


class FakeStorageAdapter:
    """Spy StoragePort double — records delete() calls; per-path behavior is
    configurable so tests can simulate a poison path (raises) or a missing
    blob (returns False)."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.raise_for: set[str] = set()
        self.missing: set[str] = set()

    async def delete(self, storage_path: str) -> bool:
        self.calls.append(storage_path)
        if storage_path in self.raise_for:
            raise RuntimeError(f"boom: storage delete failed for {storage_path}")
        return storage_path not in self.missing


async def _seed_document(
    maker: async_sessionmaker[AsyncSession],
    *,
    clan_id: uuid.UUID,
    is_deleted: bool,
    deleted_at: datetime | None,
    storage_path: str,
) -> uuid.UUID:
    doc_id = uuid.uuid4()
    created_by = uuid.uuid4()
    async with maker() as s:
        await s.execute(
            sa.text(
                "INSERT INTO documents "
                "(id, clan_id, title, document_type, storage_path, is_avatar, "
                " is_deleted, deleted_at, deleted_by, created_by) "
                "VALUES (:id, :clan, 'T', 'photo', :sp, false, :del, :da, "
                " CASE WHEN :del THEN :cb ELSE NULL END, :cb)"
            ),
            {
                "id": doc_id,
                "clan": clan_id,
                "sp": storage_path,
                "del": is_deleted,
                "da": deleted_at,
                "cb": created_by,
            },
        )
        await s.commit()
    return doc_id


@dataclass
class Seeded:
    maker: async_sessionmaker[AsyncSession]
    storage: FakeStorageAdapter
    expired_id: uuid.UUID
    poison_id: uuid.UUID
    fresh_id: uuid.UUID
    live_id: uuid.UUID
    clan_id: uuid.UUID


@pytest.fixture()
async def seeded(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[Seeded]:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)

    clan_id = uuid.uuid4()
    async with maker() as s:
        await s.execute(sa.text("DELETE FROM documents"))
        await s.execute(sa.text("DELETE FROM clans WHERE id = :id"), {"id": clan_id})
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.commit()

    now = datetime.now(UTC)
    expired_id = await _seed_document(
        maker,
        clan_id=clan_id,
        is_deleted=True,
        deleted_at=now - timedelta(days=40),
        storage_path=f"clans/{clan_id}/documents/expired.jpg",
    )
    poison_id = await _seed_document(
        maker,
        clan_id=clan_id,
        is_deleted=True,
        deleted_at=now - timedelta(days=40),
        storage_path=f"clans/{clan_id}/documents/poison.jpg",
    )
    fresh_id = await _seed_document(
        maker,
        clan_id=clan_id,
        is_deleted=True,
        deleted_at=now - timedelta(days=1),
        storage_path=f"clans/{clan_id}/documents/fresh.jpg",
    )
    live_id = await _seed_document(
        maker,
        clan_id=clan_id,
        is_deleted=False,
        deleted_at=None,
        storage_path=f"clans/{clan_id}/documents/live.jpg",
    )

    fake_storage = FakeStorageAdapter()
    monkeypatch.setattr("app.services.document_purge.SupabaseStorageAdapter", lambda: fake_storage)

    yield Seeded(
        maker=maker,
        storage=fake_storage,
        expired_id=expired_id,
        poison_id=poison_id,
        fresh_id=fresh_id,
        live_id=live_id,
        clan_id=clan_id,
    )


async def _row_count(maker: async_sessionmaker[AsyncSession], doc_id: uuid.UUID) -> int:
    async with maker() as s:
        result = await s.execute(
            sa.text("SELECT COUNT(*) FROM documents WHERE id = :id"), {"id": doc_id}
        )
        return int(result.scalar_one())


async def _is_deleted(maker: async_sessionmaker[AsyncSession], doc_id: uuid.UUID) -> bool:
    async with maker() as s:
        result = await s.execute(
            sa.text("SELECT is_deleted FROM documents WHERE id = :id"), {"id": doc_id}
        )
        return bool(result.scalar_one())


@pytest.mark.asyncio
async def test_purge_removes_expired_keeps_fresh_and_live(seeded: Seeded) -> None:
    maker, storage = seeded.maker, seeded.storage
    expired_path = f"clans/{seeded.clan_id}/documents/expired.jpg"
    poison_path = f"clans/{seeded.clan_id}/documents/poison.jpg"

    await purge_expired_documents()

    assert expired_path in storage.calls
    assert poison_path in storage.calls

    assert await _row_count(maker, seeded.expired_id) == 0
    assert await _row_count(maker, seeded.poison_id) == 0

    assert await _row_count(maker, seeded.fresh_id) == 1
    assert await _is_deleted(maker, seeded.fresh_id) is True

    assert await _row_count(maker, seeded.live_id) == 1
    assert await _is_deleted(maker, seeded.live_id) is False


@pytest.mark.asyncio
async def test_purge_isolates_per_item_failures(seeded: Seeded) -> None:
    maker, storage = seeded.maker, seeded.storage
    poison_path = f"clans/{seeded.clan_id}/documents/poison.jpg"
    storage.raise_for.add(poison_path)

    await purge_expired_documents()

    # Poison doc row survives (blob delete raised, so its row is retried next run).
    assert await _row_count(maker, seeded.poison_id) == 1
    # The other expired doc (non-poison) is still purged in the same run.
    assert await _row_count(maker, seeded.expired_id) == 0


@pytest.mark.asyncio
async def test_purge_second_run_idempotent(seeded: Seeded) -> None:
    storage = seeded.storage

    await purge_expired_documents()
    first_call_count = len(storage.calls)

    await purge_expired_documents()  # must not raise

    assert len(storage.calls) == first_call_count


@pytest.mark.asyncio
async def test_missing_blob_still_purges_row(seeded: Seeded) -> None:
    maker, storage = seeded.maker, seeded.storage
    expired_path = f"clans/{seeded.clan_id}/documents/expired.jpg"
    storage.missing.add(expired_path)

    await purge_expired_documents()

    assert await _row_count(maker, seeded.expired_id) == 0
