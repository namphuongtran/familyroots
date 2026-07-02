"""Person spouse/child stats must count only edges owned by the caller's clan.

Regression for the 2026-07-02 repository audit: get_stats_for_persons counted
marriages/parent_child with no created_by_clan_id filter, so the counts leaked the
existence of edges created by other clans.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.person_repository import SqlAlchemyPersonRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Two clans; a person p1 with a spouse + a child, all edges owned by clan_a."""
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    for cid, s in ((clan_a, f"a-{clan_a.hex[:6]}"), (clan_b, f"b-{clan_b.hex[:6]}")):
        await session.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :s)"),
            {"id": cid, "n": s, "s": s},
        )
    p1, spouse, child = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for pid in (p1, spouse, child):
        await session.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by)"
                " VALUES (:id, 'P', 'unknown', :cid, :cb)"
            ),
            {"id": pid, "cid": clan_a, "cb": uuid.uuid4()},
        )
    await session.execute(
        sa.text(
            "INSERT INTO marriages"
            " (id, person1_id, person2_id, created_by_clan_id, status, created_by)"
            " VALUES (:id, :p1, :p2, :cid, 'married', :cb)"
        ),
        {"id": uuid.uuid4(), "p1": p1, "p2": spouse, "cid": clan_a, "cb": uuid.uuid4()},
    )
    await session.execute(
        sa.text(
            "INSERT INTO parent_child"
            " (id, parent_id, child_id, created_by_clan_id, relationship_type, created_by)"
            " VALUES (:id, :p, :c, :cid, 'biological', :cb)"
        ),
        {"id": uuid.uuid4(), "p": p1, "c": child, "cid": clan_a, "cb": uuid.uuid4()},
    )
    await session.commit()
    return clan_a, clan_b, p1


@pytest.mark.asyncio
async def test_stats_scoped_to_owning_clan(async_session: AsyncSession) -> None:
    clan_a, clan_b, p1 = await _seed(async_session)
    repo = SqlAlchemyPersonRepository(
        SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    )

    # clan_a owns the edges → it sees the counts.
    stats_a = await repo.get_stats_for_persons(clan_a, [p1])
    assert stats_a[p1] == {"spouse_count": 1, "child_count": 1}

    # clan_b owns nothing → counts must be zero (no cross-clan leak).
    stats_b = await repo.get_stats_for_persons(clan_b, [p1])
    assert stats_b[p1] == {"spouse_count": 0, "child_count": 0}
