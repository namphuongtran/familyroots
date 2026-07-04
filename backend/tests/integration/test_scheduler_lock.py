"""The anniversary job is a single-runner.

Negative control: when the advisory lock is held by another instance, the job
no-ops (no send, no notification_log row). Positive control: with the lock free,
the same seeded due-event triggers a send + a log row — proving the negative
control is meaningful (it would fail if the lock gate were removed).
"""

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.database  # noqa: F401 — imported early so _reset_settings can't rebind it
from app.services import scheduler


@pytest.fixture()
async def async_engine(migrated_db_url):
    async_dsn = migrated_db_url
    engine = create_async_engine(async_dsn)
    yield engine
    await engine.dispose()


async def _seed_due_event(maker: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    """Seed a clan + a recurring event whose next occurrence is exactly
    notify_days_before (7) days away — so the job WOULD process it if it ran.

    (event_date = today + 7 → next occurrence this year is today+7 → days_until
    == notify_days_before == 7. The rare year-end wrap is out of scope for this
    test.)
    """
    clan_id = uuid.uuid4()
    event_date = date.today() + timedelta(days=7)
    async with maker() as s:
        # The migrated DB is session-scoped (shared across tests); start each run
        # from a clean slate so the global job sees only this test's event.
        await s.execute(sa.text("DELETE FROM notification_log"))
        await s.execute(sa.text("DELETE FROM events"))
        await s.commit()
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events "
                "(id, clan_id, event_type, title, event_date, is_recurring, "
                " notify_days_before, created_by) "
                "VALUES (:id, :clan, 'death_anniversary', 'Giỗ', :d, true, 7, :cb)"
            ),
            {"id": uuid.uuid4(), "clan": clan_id, "d": event_date, "cb": uuid.uuid4()},
        )
        await s.commit()
    return clan_id


@pytest.mark.asyncio
async def test_job_skips_when_lock_held(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock()
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)

    await _seed_due_event(maker)

    holder = await async_engine.connect()
    try:
        got = await holder.execute(
            sa.text("SELECT pg_try_advisory_lock(:k)"), {"k": scheduler._JOB_LOCK_KEY}
        )
        assert got.scalar() is True  # we hold the lock

        # Lock held elsewhere → the job must fail to acquire it and no-op,
        # even though a due event is present.
        await scheduler.send_anniversary_notifications()

        assert spy.await_count == 0
        async with maker() as s:
            n = await s.execute(sa.text("SELECT COUNT(*) FROM notification_log"))
            assert n.scalar() == 0
    finally:
        await holder.execute(
            sa.text("SELECT pg_advisory_unlock(:k)"), {"k": scheduler._JOB_LOCK_KEY}
        )
        await holder.close()


@pytest.mark.asyncio
async def test_job_processes_due_event_when_lock_free(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock()
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)

    await _seed_due_event(maker)

    # No lock held → the job acquires it, processes the due event, releases it.
    await scheduler.send_anniversary_notifications()

    assert spy.await_count == 1
    async with maker() as s:
        n = await s.execute(sa.text("SELECT COUNT(*) FROM notification_log"))
        assert n.scalar() == 1


async def _lock_is_free(engine: AsyncEngine) -> bool:
    """Probe from a brand-new connection; release immediately if acquired."""
    async with engine.connect() as probe:
        got = await probe.execute(
            sa.text("SELECT pg_try_advisory_lock(:k)"), {"k": scheduler._JOB_LOCK_KEY}
        )
        acquired = bool(got.scalar())
        if acquired:
            await probe.execute(
                sa.text("SELECT pg_advisory_unlock(:k)"), {"k": scheduler._JOB_LOCK_KEY}
            )
        await probe.rollback()
    return acquired


@pytest.mark.asyncio
async def test_lock_released_even_after_midjob_commit(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C2 regression: processing a due event commits mid-job; the unlock must
    still land on the lock-holding connection. Before the fix the lock was
    stranded on an idle pooled connection and later runs skipped forever."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock()
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)

    await _seed_due_event(maker)
    await scheduler.send_anniversary_notifications()  # sends + commits mid-job

    assert spy.await_count == 1
    assert await _lock_is_free(async_engine), "advisory lock stranded after mid-job commit"


@pytest.mark.asyncio
async def test_lock_released_and_error_propagates_after_failure(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C2 regression: a mid-job failure must roll back before unlocking, so the
    ORIGINAL error propagates (not InFailedSqlTransaction) and the lock frees."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    boom = RuntimeError("fcm exploded")
    monkeypatch.setattr("app.services.notification.send_to_clan", AsyncMock(side_effect=boom))

    await _seed_due_event(maker)
    with pytest.raises(RuntimeError, match="fcm exploded"):
        await scheduler.send_anniversary_notifications()

    assert await _lock_is_free(async_engine), "advisory lock stranded after job failure"
