"""M4 — the anniversary job runs on a single, injectable clock (not the DB's).

The job used Python's container-local ``date.today()`` for the "N days away" gate but
computed occurrences in SQL with ``CURRENT_DATE`` (DB server tz). When the two clocks
disagreed (near midnight / TZ mismatch) the equality gate silently MISSED. The job now
threads one ``today`` (platform timezone, injectable) into the SQL as ``:today`` with no
``CURRENT_DATE``.

The test below is discriminating: it drives the job with a FIXED ``today`` years away
from the real date. Matching therefore proves the query used ``:today`` — a residual
``CURRENT_DATE`` would compute occurrences off the real date and never hit the gate.
"""

import uuid
from collections.abc import AsyncGenerator
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
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


async def _seed_recurring_event(
    maker: async_sessionmaker[AsyncSession], *, month: int, day: int, notify_days_before: int
) -> uuid.UUID:
    clan_id = uuid.uuid4()
    async with maker() as s:
        # Shared session-scoped DB — start from a clean slate.
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
                "VALUES (:id, :clan, 'death_anniversary', 'Giỗ', :d, true, :n, :cb)"
            ),
            {
                "id": uuid.uuid4(),
                "clan": clan_id,
                "d": date(1950, month, day),  # a long-past base date; only month/day matter
                "n": notify_days_before,
                "cb": uuid.uuid4(),
            },
        )
        await s.commit()
    return clan_id


@pytest.mark.asyncio
async def test_job_matches_on_injected_today_not_db_clock(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock()
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)

    # Fixed "today" decades from the real date, so a residual CURRENT_DATE would pick a
    # different occurrence year than :today (not a coincidental match). Anniversary is
    # exactly 7 days later.
    fixed_today = date(2075, 6, 1)
    due = fixed_today + timedelta(days=7)  # 2075-06-08
    await _seed_recurring_event(maker, month=due.month, day=due.day, notify_days_before=7)

    await scheduler.send_anniversary_notifications(today=fixed_today)

    # Matched using the injected today. A CURRENT_DATE-based query would compute the
    # occurrence off the REAL date and fail the `== 7` gate → spy never called.
    assert spy.await_count == 1
    async with maker() as s:
        logged = await s.scalar(sa.text("SELECT COUNT(*) FROM notification_log"))
    assert logged == 1


@pytest.mark.asyncio
async def test_job_does_not_match_when_not_due(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock()
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)

    fixed_today = date(2075, 6, 1)
    not_due = fixed_today + timedelta(days=3)  # only 3 days away, notify_days_before=7
    await _seed_recurring_event(maker, month=not_due.month, day=not_due.day, notify_days_before=7)

    await scheduler.send_anniversary_notifications(today=fixed_today)

    assert spy.await_count == 0  # the "N days away" gate is exact w.r.t. the injected today
