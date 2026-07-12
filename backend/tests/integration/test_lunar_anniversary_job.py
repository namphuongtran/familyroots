"""Lunar giỗ reminders fire (spec 2026-07-12): the anniversary job must notify
is_lunar_calendar=true recurring events at notify_days_before, with dedup.

Mirrors the established job-test pattern (test_scheduler_robustness.py /
test_scheduler_timezone.py): the job reads ``app.core.database.engine`` /
``AsyncSessionLocal`` via a LOCAL import at call time, but those module-level
singletons are created once at import time against the real (non-test)
DATABASE_URL — ``migrated_db_url``'s ``_reset_settings`` re-points
``app.core.config.settings`` but cannot retroactively rebind an already-created
engine. So each test monkeypatches ``app.core.database.engine`` and
``AsyncSessionLocal`` to the throwaway-DB engine/sessionmaker before invoking
the job.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.database  # noqa: F401 — imported early so _reset_settings can't rebind it
from app.services.lunar_calendar import next_lunar_anniversary
from app.services.scheduler import send_anniversary_notifications

pytestmark = pytest.mark.integration

DEATH = date(2019, 4, 14)  # 10/3 âm — giỗ 2025 = 2025-04-07 (pinned in Task 1 tests)


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


async def _seed_lunar_event(
    maker: async_sessionmaker[AsyncSession], notify_days: int = 7
) -> uuid.UUID:
    clan_id = uuid.uuid4()
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
                "INSERT INTO events (id, clan_id, event_type, title, event_date, "
                "is_recurring, is_lunar_calendar, notify_days_before, created_by) "
                "VALUES (:id, :clan, 'death_anniversary', 'Giỗ cụ tổ', :d, true, true, "
                ":nd, :cb)"
            ),
            {
                "id": uuid.uuid4(),
                "clan": clan_id,
                "d": DEATH,
                "nd": notify_days,
                "cb": uuid.uuid4(),
            },
        )
        await s.commit()
    return clan_id


@pytest.mark.asyncio
async def test_lunar_gio_fires_at_notify_days_before(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)

    clan_id = await _seed_lunar_event(maker, notify_days=7)
    gio = date(2025, 4, 7)
    today = gio - timedelta(days=7)
    assert next_lunar_anniversary(DEATH, today) == gio  # sanity: engine agrees

    await send_anniversary_notifications(today=today)

    async with maker() as s:
        rows = (
            await s.execute(
                sa.text("SELECT status FROM notification_log WHERE clan_id = :c"),
                {"c": clan_id},
            )
        ).all()
    assert len(rows) == 1  # fired exactly once (status may be 'failed' — no FCM
    # tokens in test — what matters is the attempt was made)


@pytest.mark.asyncio
async def test_lunar_gio_dedup_second_run_same_day(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)

    clan_id = await _seed_lunar_event(maker, notify_days=7)
    today = date(2025, 4, 7) - timedelta(days=7)
    await send_anniversary_notifications(today=today)
    await send_anniversary_notifications(today=today)
    async with maker() as s:
        count = await s.scalar(
            sa.text("SELECT COUNT(*) FROM notification_log WHERE clan_id = :c"),
            {"c": clan_id},
        )
    assert count == 1


@pytest.mark.asyncio
async def test_one_bad_lunar_event_does_not_abort_solar_notifications(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression (Task 2 review, Finding 1): before the fix, next_occurrence for
    lunar events was precomputed in a list comprehension BEFORE the per-event loop,
    outside any try/except. One pathological event_date that makes
    next_lunar_anniversary raise therefore aborted the run before the loop even
    started — losing solar notifications for a totally unrelated clan too. The fix
    computes next_occurrence lazily INSIDE the loop's existing per-event try, so the
    bad lunar row hits the rollback-and-continue path and the solar event still
    fires."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)

    bad_date = date(1900, 1, 1)  # sentinel event_date matched by the raiser below
    real_next_lunar_anniversary = next_lunar_anniversary

    def _raising_next_lunar_anniversary(event_date: date, today_: date) -> date:
        if event_date == bad_date:
            raise ValueError("boom: pathological lunar date")
        return real_next_lunar_anniversary(event_date, today_)

    monkeypatch.setattr(
        "app.services.scheduler.next_lunar_anniversary", _raising_next_lunar_anniversary
    )

    today = date(2025, 6, 1)  # arbitrary, away from year-boundary edge cases
    solar_clan_id = uuid.uuid4()
    solar_person_id = uuid.uuid4()
    solar_due_date = today + timedelta(days=7)
    lunar_clan_id = uuid.uuid4()

    async with maker() as s:
        await s.execute(sa.text("DELETE FROM notification_log"))
        await s.execute(sa.text("DELETE FROM events"))
        await s.commit()

        # Bad lunar event, own clan — next_lunar_anniversary raises for its event_date.
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": lunar_clan_id, "sg": f"c{lunar_clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events (id, clan_id, event_type, title, event_date, "
                "is_recurring, is_lunar_calendar, notify_days_before, created_by) "
                "VALUES (:id, :clan, 'death_anniversary', 'Giỗ xấu', :d, true, true, "
                "7, :cb)"
            ),
            {"id": uuid.uuid4(), "clan": lunar_clan_id, "d": bad_date, "cb": uuid.uuid4()},
        )

        # Due solar event, unrelated clan — must still fire.
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": solar_clan_id, "sg": f"c{solar_clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, created_by, is_deleted) "
                "VALUES (:id, 'P', :cb, false)"
            ),
            {"id": solar_person_id, "cb": uuid.uuid4()},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events (id, clan_id, event_type, title, event_date, "
                "is_recurring, is_lunar_calendar, notify_days_before, person_id, "
                "created_by) "
                "VALUES (:id, :clan, 'death_anniversary', 'Giỗ tốt', :d, true, false, "
                "7, :p, :cb)"
            ),
            {
                "id": uuid.uuid4(),
                "clan": solar_clan_id,
                "d": solar_due_date,
                "p": solar_person_id,
                "cb": uuid.uuid4(),
            },
        )
        await s.commit()

    await send_anniversary_notifications(today=today)  # must not raise/lose the solar event

    async with maker() as s:
        solar_count = await s.scalar(
            sa.text("SELECT COUNT(*) FROM notification_log WHERE clan_id = :c"),
            {"c": solar_clan_id},
        )
        lunar_count = await s.scalar(
            sa.text("SELECT COUNT(*) FROM notification_log WHERE clan_id = :c"),
            {"c": lunar_clan_id},
        )
    assert solar_count == 1  # solar notification survives the bad lunar row
    assert lunar_count == 0  # bad lunar row itself was skipped, not silently "sent"


@pytest.mark.asyncio
async def test_one_real_pre_1910_lunar_event_does_not_abort_solar_notifications(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-merge review Finding 2: same isolation guarantee as
    test_one_bad_lunar_event_does_not_abort_solar_notifications, but with a REAL
    pre-1910 event_date (no monkeypatched raiser) — proves next_lunar_anniversary's
    own ValueError (SUPPORTED_MIN_YEAR guard, Finding 1) is caught by the scheduler's
    existing per-event try/except, not just a test-injected exception."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)

    pre_1910_date = date(1890, 3, 15)
    today = date(2025, 6, 1)
    solar_clan_id = uuid.uuid4()
    solar_person_id = uuid.uuid4()
    solar_due_date = today + timedelta(days=7)
    lunar_clan_id = uuid.uuid4()

    async with maker() as s:
        await s.execute(sa.text("DELETE FROM notification_log"))
        await s.execute(sa.text("DELETE FROM events"))
        await s.commit()

        # Real pre-1910 lunar event — next_lunar_anniversary raises ValueError for real.
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": lunar_clan_id, "sg": f"c{lunar_clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events (id, clan_id, event_type, title, event_date, "
                "is_recurring, is_lunar_calendar, notify_days_before, created_by) "
                "VALUES (:id, :clan, 'death_anniversary', 'Giỗ cụ tổ xa xưa', :d, true, "
                "true, 7, :cb)"
            ),
            {"id": uuid.uuid4(), "clan": lunar_clan_id, "d": pre_1910_date, "cb": uuid.uuid4()},
        )

        # Due solar event, unrelated clan — must still fire.
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": solar_clan_id, "sg": f"c{solar_clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, created_by, is_deleted) "
                "VALUES (:id, 'P', :cb, false)"
            ),
            {"id": solar_person_id, "cb": uuid.uuid4()},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events (id, clan_id, event_type, title, event_date, "
                "is_recurring, is_lunar_calendar, notify_days_before, person_id, "
                "created_by) "
                "VALUES (:id, :clan, 'death_anniversary', 'Giỗ tốt', :d, true, false, "
                "7, :p, :cb)"
            ),
            {
                "id": uuid.uuid4(),
                "clan": solar_clan_id,
                "d": solar_due_date,
                "p": solar_person_id,
                "cb": uuid.uuid4(),
            },
        )
        await s.commit()

    await send_anniversary_notifications(today=today)  # must not raise/lose the solar event

    async with maker() as s:
        solar_count = await s.scalar(
            sa.text("SELECT COUNT(*) FROM notification_log WHERE clan_id = :c"),
            {"c": solar_clan_id},
        )
        lunar_count = await s.scalar(
            sa.text("SELECT COUNT(*) FROM notification_log WHERE clan_id = :c"),
            {"c": lunar_clan_id},
        )
    assert solar_count == 1  # solar notification survives the real out-of-range lunar row
    assert lunar_count == 0  # bad lunar row itself was skipped, not silently "sent"


@pytest.mark.asyncio
async def test_lunar_gio_not_fired_on_wrong_day(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)

    clan_id = await _seed_lunar_event(maker, notify_days=7)
    today = date(2025, 4, 7) - timedelta(days=6)  # 6 days before, not 7
    await send_anniversary_notifications(today=today)
    async with maker() as s:
        count = await s.scalar(
            sa.text("SELECT COUNT(*) FROM notification_log WHERE clan_id = :c"),
            {"c": clan_id},
        )
    assert count == 0
