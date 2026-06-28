"""Person timeline projection must not leak marriage edges owned by another clan."""

import datetime
import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence.person_query_port import SqlAlchemyPersonQueryPort


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    async_dsn = migrated_db_url
    engine = create_async_engine(async_dsn)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_timeline_marriage_scoped_to_clan(async_session: AsyncSession) -> None:
    """clan_a must NOT see a marriage edge owned by clan_b that references clan_a's person."""
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    for cid, s in ((clan_a, f"a-{clan_a.hex[:6]}"), (clan_b, f"b-{clan_b.hex[:6]}")):
        await async_session.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :s)"),
            {"id": cid, "n": s, "s": s},
        )

    # p1 belongs to clan_a; p2 also seeded (spouse in clan_b's marriage)
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    for pid in (p1, p2):
        await async_session.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by)"
                " VALUES (:id, 'P', 'unknown', :cid, :cb)"
            ),
            {"id": pid, "cid": clan_a, "cb": uuid.uuid4()},
        )

    # Marriage edge owned by clan_b referencing clan_a's person p1, with a marriage_date so it
    # would surface in the timeline if the clan filter is missing.
    await async_session.execute(
        sa.text(
            "INSERT INTO marriages"
            " (id, person1_id, person2_id, created_by_clan_id, status, marriage_date, created_by)"
            " VALUES (:id, :p1, :p2, :cid, 'married', :mdate, :cb)"
        ),
        {
            "id": uuid.uuid4(),
            "p1": p1,
            "p2": p2,
            "cid": clan_b,
            "mdate": datetime.date(2000, 1, 1),
            "cb": uuid.uuid4(),
        },
    )
    await async_session.commit()

    port = SqlAlchemyPersonQueryPort(async_session)

    # clan_a must NOT see the marriage entry in the timeline
    clan_a_timeline = await port.get_timeline(clan_a, p1)
    marriage_events_a = [e for e in clan_a_timeline if e["event_type"] == "marriage"]
    assert marriage_events_a == [], (
        f"clan_a must not see clan_b's marriage in timeline, got: {marriage_events_a}"
    )

    # clan_b MUST see the marriage entry in the timeline
    clan_b_timeline = await port.get_timeline(clan_b, p1)
    marriage_events_b = [e for e in clan_b_timeline if e["event_type"] == "marriage"]
    assert len(marriage_events_b) == 1, (
        f"clan_b must see its own marriage in timeline, got: {marriage_events_b}"
    )
