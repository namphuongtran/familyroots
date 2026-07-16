"""Scheduler dedup: explicit platform-day column, uniquely indexed.

The old dedup pair was broken twice over: the query filtered
(event_id, notification_type, DATE(created_at AT TIME ZONE <platform tz>))
but the only candidate index led with user_id and hashed the UTC day — every
per-event check was a sequential scan of an ever-growing table, and the
unique backstop enforced a DIFFERENT day boundary (UTC) than the query
checked (VN). notification_log now carries `sent_on` — the platform-tz day
the scheduler decided to send for — stamped on insert and uniquely indexed
on (event_id, notification_type, sent_on).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.services.scheduler as scheduler
from app.core.config import settings

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _platform_today() -> date:
    """The scheduler computes "today" in the platform timezone (Asia/Ho_Chi_Minh).
    A UTC CI runner between 17:00-24:00 UTC is a calendar day BEHIND the platform,
    so seeding with date.today() made "due in 7 days" actually 6 platform-days out
    and the job (correctly) sent nothing — a time-of-day flake, not a code bug."""
    return datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE)).date()


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> Any:
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


async def _seed_due_event(maker: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    event_id = uuid.uuid4()
    clan_id, person_id = uuid.uuid4(), uuid.uuid4()
    async with maker() as s:
        await s.execute(sa.text("DELETE FROM notification_log"))
        await s.execute(sa.text("DELETE FROM events"))
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:i,'C',:sg)"),
            {"i": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, created_by, is_deleted) "
                "VALUES (:i, 'P', :cb, false)"
            ),
            {"i": person_id, "cb": uuid.uuid4()},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events (id, clan_id, event_type, title, event_date, "
                "is_recurring, is_lunar_calendar, notify_days_before, person_id, created_by) "
                "VALUES (:i,:c,'death_anniversary','Giỗ',:d,true,false,7,:p,:cb)"
            ),
            {
                "i": event_id,
                "c": clan_id,
                "d": _platform_today() + timedelta(days=7),
                "p": person_id,
                "cb": uuid.uuid4(),
            },
        )
        await s.commit()
    return event_id


async def test_scheduler_stamps_sent_on_with_platform_day(
    async_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    monkeypatch.setattr("app.services.notification.send_to_clan", AsyncMock(return_value=(1, 0)))
    await _seed_due_event(maker)

    await scheduler.send_anniversary_notifications()

    async with maker() as s:
        row = (await s.execute(sa.text("SELECT sent_on FROM notification_log"))).one()
    assert row.sent_on is not None  # stamped, not left to created_at tz math


async def test_dedup_survives_second_run(
    async_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)
    await _seed_due_event(maker)

    await scheduler.send_anniversary_notifications()
    await scheduler.send_anniversary_notifications()

    assert spy.await_count == 1  # second run deduped
    async with maker() as s:
        count = await s.scalar(sa.text("SELECT COUNT(*) FROM notification_log"))
    assert count == 1


async def test_unique_index_enforces_event_type_day(async_engine: Any) -> None:
    """The DB backstop must reject a duplicate (event_id, type, sent_on) —
    the old index led with user_id and a UTC date expression, so it enforced
    a different boundary than the dedup query checked."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    event_id = await _seed_due_event(maker)

    async def _insert(s: AsyncSession) -> None:
        await s.execute(
            sa.text(
                "INSERT INTO notification_log (clan_id, event_id, user_id, notification_type, "
                " title, body, status, sent_on) "
                "SELECT clan_id, :eid, '00000000-0000-0000-0000-000000000000', "
                "       'death_anniversary', 'Giỗ', '', 'sent', :day FROM events WHERE id = :eid"
            ),
            {"eid": event_id, "day": _platform_today()},
        )

    async with maker() as s:
        await _insert(s)
        await s.commit()
    async with maker() as s:
        with pytest.raises(IntegrityError):
            await _insert(s)
            await s.commit()
