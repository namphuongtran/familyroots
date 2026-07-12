"""ADR-019 purge: soft-deleted documents past retention lose blob + row;
fresh deletions and live documents are untouched; failures are isolated.

Fixture style mirrors tests/integration/test_lunar_anniversary_job.py: monkeypatch
app.core.database.engine to the migrated throwaway DB, seed via raw SQL. The storage
adapter's delete() is monkeypatched at the purge module's import seam
(app.services.document_purge.SupabaseStorageAdapter) with a spy that records calls
and can be told to raise (StorageError) or confirm not-found (returns True — the
StoragePort contract, per FIX 2 of the task 3 review, no longer has a False case:
"not found" and "deleted" are both success) per path.

The per-item flow is claim-row -> delete-blob -> commit (owner decision
2026-07-12, FIX 1 of the task 3 review): the guarded per-row DELETE (id +
is_deleted=true + deleted_at<cutoff) claims the row before the blob is
touched, and the transaction only commits after the blob delete succeeds. See
test_restore_race_between_snapshot_and_claim_is_safe for the race this
protects against.
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
from app.domain.document.repository import StorageError
from app.services.document_purge import purge_expired_documents

pytestmark = pytest.mark.integration


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


class FakeStorageAdapter:
    """Spy StoragePort double — records delete() calls; per-path behavior is
    configurable so tests can simulate a poison path (raises StorageError) or
    a confirmed-missing blob (still returns True — the StoragePort contract
    treats "already gone" as success, not a distinct failure case)."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.raise_for: set[str] = set()
        self.missing: set[str] = set()

    async def delete(self, storage_path: str) -> bool:
        self.calls.append(storage_path)
        if storage_path in self.raise_for:
            raise StorageError(f"boom: storage delete failed for {storage_path}")
        # storage_path in self.missing simulates a confirmed-not-found blob —
        # under the new contract that's still True (success), same as an
        # actually-present blob being deleted. Kept as a distinct set purely
        # to document test intent (see test_missing_blob_still_purges_row).
        return True


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

    # Poison doc row survives: its claim committed nothing because the blob
    # delete raised StorageError inside the (still-open) claimed transaction,
    # rolling the claim back — the row is retried next run, never orphaned.
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
    """Confirmed-not-found is success under the StoragePort contract (FIX 2):
    delete() returns True even when the blob is already gone, so the claimed
    row is still purged — a missing blob is not a failure."""
    maker, storage = seeded.maker, seeded.storage
    expired_path = f"clans/{seeded.clan_id}/documents/expired.jpg"
    storage.missing.add(expired_path)

    await purge_expired_documents()

    assert await _row_count(maker, seeded.expired_id) == 0


@pytest.mark.asyncio
async def test_missing_blob_delete_error_row_survives(seeded: Seeded) -> None:
    """The mirror case: when the blob delete raises (a transport/unexpected
    failure that can't be distinguished from "actually still there"), the
    already-claimed row must NOT be purged — the claim rolls back and the row
    survives for the next run, even though the underlying blob might already
    be gone."""
    maker, storage = seeded.maker, seeded.storage
    expired_path = f"clans/{seeded.clan_id}/documents/expired.jpg"
    storage.raise_for.add(expired_path)

    await purge_expired_documents()

    assert await _row_count(maker, seeded.expired_id) == 1
    assert await _is_deleted(maker, seeded.expired_id) is True


@pytest.mark.asyncio
async def test_restore_race_between_snapshot_and_claim_is_safe(seeded: Seeded) -> None:
    """Regression for the restore/purge race (FIX 1, task 3 review).

    The batch SELECT snapshots eligible rows once at the top of the job; each
    row is then claimed individually (guarded DELETE) before its blob is
    touched. If a restore commits *after* the snapshot but *before* a given
    row's own claim runs, that row's claim rowcount is 0 (is_deleted flipped
    back to false) — it must be skipped entirely, blob untouched, row intact.

    Deterministic without real concurrency: the purge SELECT is `ORDER BY
    deleted_at ASC`, so `poison_id` (backdated to be older here) is claimed
    and its blob deleted first. The storage spy, when called to delete
    poison's blob — i.e. strictly after poison's own claim succeeded but
    before poison's commit, and strictly before `expired_id`'s turn in the
    loop — reaches into a second, independent session and restores
    `expired_id`. That lands the restore exactly in the window between the
    batch snapshot (which included `expired_id`) and `expired_id`'s own
    per-row claim.
    """
    maker, storage = seeded.maker, seeded.storage
    expired_path = f"clans/{seeded.clan_id}/documents/expired.jpg"
    poison_path = f"clans/{seeded.clan_id}/documents/poison.jpg"

    # Both were seeded with the same deleted_at; backdate poison so ORDER BY
    # deleted_at ASC claims and processes it strictly before expired_id.
    async with maker() as s:
        await s.execute(
            sa.text(
                "UPDATE documents SET deleted_at = deleted_at - interval '1 day' WHERE id = :id"
            ),
            {"id": seeded.poison_id},
        )
        await s.commit()

    restored = {"done": False}
    real_delete = storage.delete

    async def racing_delete(storage_path: str) -> bool:
        result = await real_delete(storage_path)
        if storage_path == poison_path and not restored["done"]:
            restored["done"] = True
            # Independent session — not the purge job's own connection — so
            # this does not contend with any lock the job's claim holds.
            async with maker() as s2:
                await s2.execute(
                    sa.text(
                        "UPDATE documents SET is_deleted = false, deleted_at = NULL WHERE id = :id"
                    ),
                    {"id": seeded.expired_id},
                )
                await s2.commit()
        return result

    storage.delete = racing_delete  # type: ignore[method-assign]

    await purge_expired_documents()

    # expired_id's own claim found rowcount=0 (restored mid-run): it survives,
    # untouched, and its blob was never even attempted.
    assert await _row_count(maker, seeded.expired_id) == 1
    assert await _is_deleted(maker, seeded.expired_id) is False
    assert expired_path not in storage.calls

    # poison's own claim + blob delete completed normally in the same run.
    assert await _row_count(maker, seeded.poison_id) == 0
    assert poison_path in storage.calls
