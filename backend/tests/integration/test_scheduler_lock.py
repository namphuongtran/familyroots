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
    AsyncConnection,
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


# NOTE (C2 review): the two tests below assert only the POST-CONDITION —
# that the advisory lock is free after the job runs. In pytest's serial,
# single-pool-connection harness that post-condition holds against BOTH the
# fixed (dedicated-connection) code and the pre-fix code that bound the
# working session directly to the engine via AsyncSessionLocal(): the strand
# only manifests under real concurrent pool contention, which this harness
# never exercises. So these two tests give false regression confidence on
# their own — a revert to the pre-fix pattern would stay green here. The
# `test_lock_and_unlock_run_on_one_dedicated_connection` test further below
# is what actually guards the un-strandable lock TOPOLOGY (one dedicated
# connection, acquire+release on that same connection) and genuinely fails
# on such a revert.
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
    """C2 regression: a mid-job failure must roll back before unlocking, so the
    ORIGINAL error propagates (not InFailedSqlTransaction) and the lock frees."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    # Inject a JOB-FATAL error (not a per-event send_to_clan failure, which S2-3 now
    # isolates and swallows): corrupt the SQL fragment that next_anniversary_sql feeds
    # into the events-fetch query. next_anniversary_sql runs BEFORE engine.connect(), so
    # we must RETURN invalid SQL (not raise) — the raise would then land in the fetch
    # db.execute() INSIDE the outer try, AFTER the lock is acquired, exercising the
    # rollback→unlock release path in the finally block.
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


@pytest.mark.asyncio
async def test_lock_and_unlock_run_on_one_dedicated_connection(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Discriminating regression test (C2 review).

    The two tests above only check that the lock ends up free — a check that
    passes against BOTH the fixed code and the pre-fix
    ``async with AsyncSessionLocal() as db:`` version, because the strand
    those pre-fix code paths caused only manifests under real pool
    contention, which this serial harness never exercises. This test instead
    asserts the LOCK TOPOLOGY directly, which the pre-fix code cannot satisfy
    even in a serial harness:

    1. the job opens exactly ONE dedicated connection via
       ``engine.connect()`` for the whole run, and
    2. both the ``pg_try_advisory_lock`` acquire and the
       ``pg_advisory_unlock`` release execute on THAT SAME connection.

    The pre-fix code never called ``engine.connect()`` at all — it acquired
    and released the lock through sessions pulled from
    ``AsyncSessionLocal()`` (i.e. from the engine's pool), so a revert to
    that pattern makes ``opened`` empty and this test fails immediately,
    with no need for concurrency to expose the bug.
    """
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)

    today = _platform_today()
    await _seed_due_event(maker, today=today)

    opened: list[AsyncConnection] = []
    lock_sql_by_conn_id: dict[int, list[str]] = {}

    # AsyncEngine/AsyncConnection use __slots__, so we can't stash spies on a
    # specific instance — patch the class methods instead and disambiguate by
    # the id() of the connection object each call actually landed on.
    real_connect = AsyncEngine.connect
    real_execute = AsyncConnection.execute

    def spying_connect(self: AsyncEngine) -> AsyncConnection:
        conn = real_connect(self)
        opened.append(conn)
        return conn

    async def spying_execute(self: AsyncConnection, clause, *args, **kwargs):  # type: ignore[no-untyped-def]
        sql_text = str(clause)
        if "pg_try_advisory_lock" in sql_text or "pg_advisory_unlock" in sql_text:
            lock_sql_by_conn_id.setdefault(id(self), []).append(sql_text)
        return await real_execute(self, clause, *args, **kwargs)

    monkeypatch.setattr(AsyncEngine, "connect", spying_connect)
    monkeypatch.setattr(AsyncConnection, "execute", spying_execute)

    await scheduler.send_anniversary_notifications(today=today)

    assert spy.await_count == 1  # sanity: the due event was actually processed

    assert len(opened) == 1, (
        f"expected exactly one dedicated engine.connect() call for the lock, got {len(opened)} "
        "— the pre-fix AsyncSessionLocal()-bound-session pattern calls engine.connect() zero "
        "times, so this is the assertion a revert fails"
    )
    dedicated_conn_id = id(opened[0])
    calls_on_dedicated_conn = lock_sql_by_conn_id.get(dedicated_conn_id, [])

    assert any("pg_try_advisory_lock" in c for c in calls_on_dedicated_conn), (
        "advisory-lock acquire did not run on the dedicated connection"
    )
    assert any("pg_advisory_unlock" in c for c in calls_on_dedicated_conn), (
        "advisory-lock release did not run on the dedicated connection"
    )
    # No connection OTHER than the dedicated one ever touched the lock/unlock
    # functions — i.e. acquire and release genuinely share one connection.
    assert set(lock_sql_by_conn_id.keys()) == {dedicated_conn_id}
