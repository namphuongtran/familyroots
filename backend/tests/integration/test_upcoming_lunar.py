"""/events/upcoming must show the CONVERTED solar date for lunar recurring events
(it previously applied the solar anniversary formula to them — wrong date)."""

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.event_repository import SqlAlchemyEventRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration

DEATH = date(2019, 4, 14)  # 10/3 âm → giỗ 2025 = 2025-04-07 (pinned, Task 1)


async def _seed(maker):
    clan_id = uuid.uuid4()
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        for d, lunar in [(DEATH, True), (date(2020, 4, 20), False)]:
            await s.execute(
                sa.text(
                    "INSERT INTO events (id, clan_id, event_type, title, event_date, "
                    "is_recurring, is_lunar_calendar, notify_days_before, created_by) "
                    "VALUES (:id, :clan, 'death_anniversary', :t, :d, true, :lu, 7, :cb)"
                ),
                {
                    "id": uuid.uuid4(),
                    "clan": clan_id,
                    "t": f"lunar={lunar}",
                    "d": d,
                    "lu": lunar,
                    "cb": uuid.uuid4(),
                },
            )
        await s.commit()
    return clan_id


async def test_upcoming_lunar_uses_converted_date_and_merges_sorted(migrated_db_url):
    eng = create_async_engine(migrated_db_url)
    try:
        maker = async_sessionmaker(eng, expire_on_commit=False)
        clan_id = await _seed(maker)
        async with maker() as s:
            repo = SqlAlchemyEventRepository(SqlAlchemyUnitOfWork(s, create_event_dispatcher(s)))
            rows = await repo.get_upcoming(
                clan_id, today=date(2025, 4, 1), end_date=date(2025, 4, 30), limit=10
            )
        by_title = {r["title"]: r for r in rows}
        # HARD-CODED expected conversion — not recomputed via the engine here:
        assert by_title["lunar=True"]["next_occurrence"] == "2025-04-07"
        assert by_title["lunar=True"]["days_until"] == 6
        assert by_title["lunar=True"]["is_lunar_calendar"] is True
        # solar event: plain solar anniversary 2025-04-20
        assert by_title["lunar=False"]["next_occurrence"] == "2025-04-20"
        # merged ordering by next_occurrence
        assert [r["title"] for r in rows] == ["lunar=True", "lunar=False"]
    finally:
        await eng.dispose()


async def _seed_pre_1910_and_normal(maker):
    """One pre-1910 lunar recurring event (next_lunar_anniversary raises for real —
    Finding 1's SUPPORTED_MIN_YEAR guard) alongside one normal lunar recurring event,
    both in the same clan — used to prove get_upcoming skips the bad row instead of
    the whole endpoint 500ing (pre-merge review, Finding 2)."""
    clan_id = uuid.uuid4()
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        for d, title in [(date(1890, 3, 15), "too-old"), (DEATH, "normal")]:
            await s.execute(
                sa.text(
                    "INSERT INTO events (id, clan_id, event_type, title, event_date, "
                    "is_recurring, is_lunar_calendar, notify_days_before, created_by) "
                    "VALUES (:id, :clan, 'death_anniversary', :t, :d, true, true, 7, :cb)"
                ),
                {
                    "id": uuid.uuid4(),
                    "clan": clan_id,
                    "t": title,
                    "d": d,
                    "cb": uuid.uuid4(),
                },
            )
        await s.commit()
    return clan_id


async def test_upcoming_lunar_skips_pre_1910_row_without_raising(migrated_db_url):
    eng = create_async_engine(migrated_db_url)
    try:
        maker = async_sessionmaker(eng, expire_on_commit=False)
        clan_id = await _seed_pre_1910_and_normal(maker)
        async with maker() as s:
            repo = SqlAlchemyEventRepository(SqlAlchemyUnitOfWork(s, create_event_dispatcher(s)))
            rows = await repo.get_upcoming(
                clan_id, today=date(2025, 4, 1), end_date=date(2025, 4, 30), limit=10
            )
        titles = {r["title"] for r in rows}
        assert titles == {"normal"}  # the pre-1910 row was skipped, not raised
    finally:
        await eng.dispose()


async def test_upcoming_lunar_outside_window_excluded(migrated_db_url):
    eng = create_async_engine(migrated_db_url)
    try:
        maker = async_sessionmaker(eng, expire_on_commit=False)
        clan_id = await _seed(maker)
        async with maker() as s:
            repo = SqlAlchemyEventRepository(SqlAlchemyUnitOfWork(s, create_event_dispatcher(s)))
            rows = await repo.get_upcoming(
                clan_id, today=date(2025, 4, 10), end_date=date(2025, 4, 15), limit=10
            )
        # giỗ 2025 already passed; giỗ 2026 is beyond this window.
        assert all(r["title"] != "lunar=True" for r in rows)
    finally:
        await eng.dispose()
