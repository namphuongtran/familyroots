"""The anniversary job is a single-runner.

Negative control: when the advisory lock is held by another instance, the job
no-ops (no send, no notification_log row). Positive control: with the lock free,
the same seeded due-event triggers a send + a log row — proving the negative
control is meaningful (it would fail if the lock gate were removed).
"""

import uuid
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.database  # noqa: F401 — imported early so _reset_settings can't rebind it
from app.core.config import settings
from app.services import scheduler


def _platform_today() -> date:
    """The job computes 'today' in the platform timezone (M4), so tests must seed and
    invoke on that SAME clock — using the container-local date.today() drifts by a day
    whenever the two zones straddle midnight (e.g. CI running in the UTC evening)."""
    return datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE)).date()


@pytest.fixture()
async def async_engine(migrated_db_url):
    async_dsn = migrated_db_url
    engine = create_async_engine(async_dsn)
    yield engine
    await engine.dispose()


async def _seed_due_event(maker: async_sessionmaker[AsyncSession], *, today: date) -> uuid.UUID:
    """Seed a clan + a recurring event whose next occurrence is exactly
    notify_days_before (7) days away — so the job WOULD process it if it ran.

    (event_date = today + 7 → next occurrence this year is today+7 → days_until
    == notify_days_before == 7. The rare year-end wrap is out of scope for this
    test.) ``today`` is the platform-zone date shared with the job call.
    """
    clan_id = uuid.uuid4()
    event_date = today + timedelta(days=7)
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
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)

    today = _platform_today()
    await _seed_due_event(maker, today=today)

    holder = await async_engine.connect()
    try:
        got = await holder.execute(
            sa.text("SELECT pg_try_advisory_lock(:k)"), {"k": scheduler._JOB_LOCK_KEY}
        )
        assert got.scalar() is True  # we hold the lock

        # Lock held elsewhere → the job must fail to acquire it and no-op,
        # even though a due event is present.
        await scheduler.send_anniversary_notifications(today=today)

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
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)

    today = _platform_today()
    await _seed_due_event(maker, today=today)

    # No lock held → the job acquires it, processes the due event, releases it.
    await scheduler.send_anniversary_notifications(today=today)

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


# NOTE (ADR-065): the two tests below assert only the POST-CONDITION, that the
# advisory lock is free after the job runs, probed through the job's own engine. On a
# direct Postgres that post-condition holds for the transaction-scoped lock the jobs
# take now AND for the C2 session-level lock they took before, which unlocked on its own
# connection, so these two cannot tell those topologies apart. They do fail when the
# unlock lands on another connection, but only because their probe happens to land on a
# connection that does not own the leaked lock. The tests built to read that outcome are
# in test_job_lock_survives_a_pooler.py:
# a concurrent run that must skip, and a later run on a second engine that must take
# the lock. The second engine is what models a transaction pooler, whose server
# connections outlive the client. (The C2 topology test that used to close this file
# asserted that `pg_advisory_unlock` ran on the dedicated connection. The jobs no
# longer unlock at all, because the lock ends with its transaction, so it went.)
@pytest.mark.asyncio
async def test_lock_released_even_after_midjob_commit(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Processing a due event commits mid-job, on the work session; the lock must be
    free afterwards. (C2 regression, originally: before C2 the lock was stranded on an
    idle pooled connection and later runs skipped forever.)"""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)

    today = _platform_today()
    await _seed_due_event(maker, today=today)
    await scheduler.send_anniversary_notifications(today=today)  # sends + commits mid-job

    assert spy.await_count == 1
    assert await _lock_is_free(async_engine), "advisory lock stranded after mid-job commit"


@pytest.mark.asyncio
async def test_lock_released_and_error_propagates_after_failure(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A job-fatal error on the work session propagates as itself, and the lock still
    frees. Since ADR-065 the lock connection runs nothing after the lock, so ending its
    transaction cannot meet InFailedSqlTransaction and mask the job's error."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    # Inject a JOB-FATAL error (not a per-event send_to_clan failure, which S2-3 now
    # isolates and swallows): corrupt the SQL fragment that next_anniversary_sql feeds
    # into the events-fetch query. next_anniversary_sql runs BEFORE engine.connect(), so
    # we must RETURN invalid SQL (not raise) — the raise would then land in the fetch
    # db.execute() INSIDE the outer try, AFTER the lock is acquired, exercising the
    # lock-transaction rollback in the finally block, which is what releases the lock.
    monkeypatch.setattr(
        "app.infrastructure.persistence.sql_dates.next_anniversary_sql",
        lambda *a, **k: "(this_is_not_valid_sql",
    )

    today = _platform_today()
    await _seed_due_event(maker, today=today)
    with pytest.raises(Exception):  # noqa: B017 — DB error type is driver-specific; the
        # point is that a job-fatal error propagates out at all (C2 guarantee).
        await scheduler.send_anniversary_notifications(today=today)

    assert await _lock_is_free(async_engine), "advisory lock stranded after job failure"
