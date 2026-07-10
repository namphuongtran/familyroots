"""Scheduler: lunar events excluded, soft-deleted persons skipped, per-event isolation,
truthful log status."""

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.database  # noqa: F401
from app.services import scheduler


@pytest.fixture()
async def async_engine(migrated_db_url):
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


async def _seed_event(
    maker: async_sessionmaker[AsyncSession],
    *,
    lunar: bool = False,
    person_deleted: bool = False,
) -> uuid.UUID:
    clan_id, person_id = uuid.uuid4(), uuid.uuid4()
    event_date = date.today() + timedelta(days=7)
    async with maker() as s:
        await s.execute(sa.text("DELETE FROM notification_log"))
        await s.execute(sa.text("DELETE FROM events"))
        await s.commit()
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:i,'C',:sg)"),
            {"i": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, created_by, is_deleted) "
                "VALUES (:i, 'P', :cb, :d)"
            ),
            {"i": person_id, "cb": uuid.uuid4(), "d": person_deleted},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events (id, clan_id, event_type, title, event_date, is_recurring, "
                "is_lunar_calendar, notify_days_before, person_id, created_by) "
                "VALUES (:i,:c,'death_anniversary','Giỗ',:d,true,:lu,7,:p,:cb)"
            ),
            {
                "i": uuid.uuid4(),
                "c": clan_id,
                "d": event_date,
                "lu": lunar,
                "p": person_id,
                "cb": uuid.uuid4(),
            },
        )
        await s.commit()
    return clan_id


@pytest.mark.asyncio
async def test_lunar_event_is_excluded(async_engine, monkeypatch):
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)
    await _seed_event(maker, lunar=True)
    await scheduler.send_anniversary_notifications()
    assert spy.await_count == 0  # lunar event not broadcast


@pytest.mark.asyncio
async def test_soft_deleted_person_is_skipped(async_engine, monkeypatch):
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)
    await _seed_event(maker, person_deleted=True)
    await scheduler.send_anniversary_notifications()
    assert spy.await_count == 0


@pytest.mark.asyncio
async def test_failed_delivery_logs_failed_status(async_engine, monkeypatch):
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    monkeypatch.setattr("app.services.notification.send_to_clan", AsyncMock(return_value=(0, 2)))
    await _seed_event(maker)
    await scheduler.send_anniversary_notifications()
    async with maker() as s:
        status = await s.scalar(sa.text("SELECT status FROM notification_log LIMIT 1"))
    assert status == "failed"
