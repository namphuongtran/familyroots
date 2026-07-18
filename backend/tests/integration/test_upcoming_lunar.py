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


async def _seed_with_person(maker):
    """A clan, a person, and one NORMAL (non-lunar, non-recurring) upcoming solar
    event linked to that person — so get_upcoming's person LEFT JOIN populates
    person_id/person_name/person_avatar_url and the route's include=person block
    has something to shape."""
    clan_id, person_id, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                "VALUES (:id, :n, 'unknown', :cid, :cb)"
            ),
            {"id": person_id, "n": "Nguyen Van A", "cid": clan_id, "cb": actor},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events (id, clan_id, person_id, event_type, title, event_date, "
                "is_recurring, is_lunar_calendar, notify_days_before, created_by) "
                "VALUES (:id, :clan, :pid, 'birthday', 'normal', :d, false, false, 7, :cb)"
            ),
            {
                "id": uuid.uuid4(),
                "clan": clan_id,
                "pid": person_id,
                "d": date(2025, 4, 20),
                "cb": actor,
            },
        )
        await s.commit()
    return clan_id


async def test_upcoming_wire_matches_upcoming_event_schema(migrated_db_url):
    """Coherence guard: /events/upcoming hand-builds its item dicts (and the
    optional `person` sub-object), so the documentation-only UpcomingEvent schema
    can drift from the route output. Validate a real body — including the
    person-include shaping the route applies — against UpcomingEvent."""
    from app.application.event.handlers import EventQueryHandler
    from app.schemas.event import UpcomingEvent

    eng = create_async_engine(migrated_db_url)
    try:
        maker = async_sessionmaker(eng, expire_on_commit=False)
        clan_id = await _seed_with_person(maker)
        async with maker() as s:
            repo = SqlAlchemyEventRepository(SqlAlchemyUnitOfWork(s, create_event_dispatcher(s)))
            handler = EventQueryHandler(repo)
            today = date(2025, 4, 1)
            upcoming = await handler.get_upcoming(clan_id=clan_id, days=30, today=today)

        assert upcoming  # non-empty so the loop actually runs

        # Mirror the route's include=person block (app/api/v1/events.py::get_upcoming_events):
        for item in upcoming:
            if item.get("person_id") and item.get("person_name"):
                item["person"] = {
                    "id": item["person_id"],
                    "full_name": item["person_name"],
                    "avatar_url": item.get("person_avatar_url"),
                }
            else:
                item["person"] = None
            UpcomingEvent.model_validate(item)  # raises on drift
    finally:
        await eng.dispose()
