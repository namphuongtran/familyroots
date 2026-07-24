"""C2 regression (seam-review-2026-07-04): Feb-29 recurring events must not
crash occurrence computation; non-leap years observe Feb 28 (owner decision).

Before the fix, MAKE_DATE(year, 2, 29) raised 'date field value out of range',
aborting the scheduler's whole SELECT (killing the nightly job for every clan)
and the /events/upcoming query.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.event_repository import SqlAlchemyEventRepository
from app.infrastructure.persistence.sql_dates import next_anniversary_sql
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_sql_fragment_clamps_feb_29(engine: AsyncEngine) -> None:
    """The shared fragment: Feb-29 anniversary in 2026 (non-leap) → Feb 28;
    in 2028 (leap) → Feb 29; ordinary dates pass through unchanged."""
    frag = next_anniversary_sql(":year", date_col=":d ::date")
    async with engine.connect() as conn:
        for year, event_date, expected in [
            (2026, date(2024, 2, 29), date(2026, 2, 28)),
            (2028, date(2024, 2, 29), date(2028, 2, 29)),
            (2026, date(2020, 3, 10), date(2026, 3, 10)),
            (2026, date(2019, 12, 31), date(2026, 12, 31)),
        ]:
            got = await conn.scalar(sa.text(f"SELECT {frag}"), {"year": year, "d": event_date})
            assert got == expected, f"{event_date} in {year}: {got} != {expected}"


async def _seed_clan_with_feb29_event(
    maker: async_sessionmaker[AsyncSession],
) -> uuid.UUID:
    clan_id = uuid.uuid4()
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events (id, clan_id, event_type, title, event_date, "
                "is_recurring, notify_days_before, created_by) "
                "VALUES (:id, :clan, 'death_anniversary', 'Giỗ 29/2', :d, true, 7, :cb)"
            ),
            {"id": uuid.uuid4(), "clan": clan_id, "d": date(2024, 2, 29), "cb": uuid.uuid4()},
        )
        await s.commit()
    return clan_id


async def _seed_clan_with_circa_event(
    maker: async_sessionmaker[AsyncSession],
) -> uuid.UUID:
    """A NON-RECURRING future event whose recorded date has a non-'exact' precision +
    display, to prove /events/upcoming's `event_date` carries the real stored
    precision/display instead of silently defaulting to 'exact' (historical-date review,
    task 5). Must be non-recurring: since M4 (2026-07), a non-exact RECURRING event is
    excluded from /upcoming (no real anniversary to notify); a non-exact ONE-OFF future
    event still appears, which is what this test needs."""
    clan_id = uuid.uuid4()
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events (id, clan_id, event_type, title, event_date, "
                "event_date_precision, event_date_display, "
                "is_recurring, notify_days_before, created_by) "
                "VALUES (:id, :clan, 'custom', 'Circa event', :d, "
                "'circa', 'khoảng tháng 6/2026', false, 7, :cb)"
            ),
            {"id": uuid.uuid4(), "clan": clan_id, "d": date(2026, 6, 15), "cb": uuid.uuid4()},
        )
        await s.commit()
    return clan_id


@pytest.mark.asyncio
async def test_get_upcoming_survives_feb29_and_clamps(engine: AsyncEngine) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    clan_id = await _seed_clan_with_feb29_event(maker)

    async with maker() as s:
        uow = SqlAlchemyUnitOfWork(s, create_event_dispatcher(s))
        repo = SqlAlchemyEventRepository(uow)
        # A window in a NON-leap year that covers Feb 28: the event must appear,
        # clamped — before the fix this raised DataError.
        rows = await repo.get_upcoming(clan_id, today=date(2026, 2, 20), end_date=date(2026, 3, 20))
    # get_upcoming serializes dates to ISO strings (API response shape).
    occurrences = {r["next_occurrence"] for r in rows}
    assert date(2026, 2, 28).isoformat() in occurrences


@pytest.mark.asyncio
async def test_get_upcoming_event_date_is_historical_date_object(engine: AsyncEngine) -> None:
    """/events/upcoming (task 5, historical-date review): `event_date` must be a nested
    HistoricalDate object carrying the real stored precision + display — not a scalar
    ISO string, and not silently defaulted to 'exact'. `next_occurrence` (the derived
    recurrence date) stays a scalar ISO string."""
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    clan_id = await _seed_clan_with_circa_event(maker)

    async with maker() as s:
        uow = SqlAlchemyUnitOfWork(s, create_event_dispatcher(s))
        repo = SqlAlchemyEventRepository(uow)
        rows = await repo.get_upcoming(clan_id, today=date(2026, 6, 1), end_date=date(2026, 7, 1))

    assert len(rows) == 1
    row = rows[0]

    # RED (pre-fix) behavior would be: row["event_date"] == "1950-06-15" (a str).
    # GREEN (post-fix): a nested HistoricalDate dict with the real precision/display.
    # (`date` stays a python `date` object here, same as tree_builder/person_query_port's
    # plain `.model_dump()`; FastAPI's jsonable_encoder ISO-formats it at the HTTP layer.)
    event_date = row["event_date"]
    assert isinstance(event_date, dict), f"event_date must be an object, got {event_date!r}"
    assert event_date == {
        "date": date(2026, 6, 15),
        "precision": "circa",
        "display": "khoảng tháng 6/2026",
        "lunar": None,
    }
    # next_occurrence is the derived recurrence date — remains a scalar ISO string.
    # For a one-off event it is the event's own date.
    assert row["next_occurrence"] == date(2026, 6, 15).isoformat()
