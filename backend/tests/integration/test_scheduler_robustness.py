"""Scheduler: lunar events fire via the VN lunar engine (Task 2, lunar-gio), soft-deleted
persons skipped, per-event isolation, truthful log status."""

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


async def _seed_two_due_events(maker: async_sessionmaker[AsyncSession]) -> None:
    """Seed TWO independent due events (separate clans/persons), both non-lunar,
    non-deleted, with event_date = today + 7 days and notify_days_before=7 — used to
    prove one event raising inside the loop doesn't stop the other from being
    processed."""
    event_date = date.today() + timedelta(days=7)
    async with maker() as s:
        await s.execute(sa.text("DELETE FROM notification_log"))
        await s.execute(sa.text("DELETE FROM events"))
        await s.commit()
        for _ in range(2):
            clan_id, person_id = uuid.uuid4(), uuid.uuid4()
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
                    "is_recurring, is_lunar_calendar, notify_days_before, person_id, "
                    "created_by) "
                    "VALUES (:i,:c,'death_anniversary','Giỗ',:d,true,false,7,:p,:cb)"
                ),
                {
                    "i": uuid.uuid4(),
                    "c": clan_id,
                    "d": event_date,
                    "p": person_id,
                    "cb": uuid.uuid4(),
                },
            )
        await s.commit()


@pytest.mark.asyncio
async def test_one_bad_event_does_not_abort_run(async_engine, monkeypatch):
    """PR-H T4: the per-event try/except in send_anniversary_notifications must
    isolate one event's failure from the rest of the run — the first due event's
    broadcast raises, the second must still be processed and logged."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    monkeypatch.setattr(
        "app.services.notification.send_to_clan",
        AsyncMock(side_effect=[RuntimeError("boom"), (1, 0)]),
    )
    await _seed_two_due_events(maker)

    await scheduler.send_anniversary_notifications()  # must not raise/propagate

    async with maker() as s:
        count = await s.scalar(sa.text("SELECT COUNT(*) FROM notification_log"))
    # Only the surviving event logged; the failed event's insert was rolled back.
    assert count == 1


@pytest.mark.asyncio
async def test_lunar_event_is_included(async_engine, monkeypatch):
    """Lunar-gio (Task 2): is_lunar_calendar=true recurring events are now processed
    through next_lunar_anniversary just like solar ones — the round-2-deferral this
    test used to pin is gone. See test_lunar_anniversary_job.py for the dedicated
    lunar-engine coverage (giỗ-date pinning, dedup, wrong-day exclusion)."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)
    await _seed_event(maker, lunar=True)
    await scheduler.send_anniversary_notifications()
    assert spy.await_count == 1  # lunar event now broadcast (fires via lunar engine)


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
async def test_lunar_soft_deleted_person_is_skipped(async_engine, monkeypatch):
    """Lunar variant of test_soft_deleted_person_is_skipped: a lunar recurring event
    whose person is soft-deleted must be excluded by the same
    ``p.is_deleted = false`` join filter the lunar query shares with the solar one —
    the event never reaches next_lunar_anniversary or the notification path."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)
    await _seed_event(maker, lunar=True, person_deleted=True)
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
