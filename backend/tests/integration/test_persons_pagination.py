"""Real-DB regression for F-1 5a: GET /persons meta pagination (cursor/has_more).

Seeds more persons than the page limit and drives PersonQueryHandler.list_persons
(the same code path the route calls) across two pages via the real migrated schema.

Note: list_in_clan orders by full_name but paginates by an id-cursor — a known,
pre-existing stability mismatch (out of scope for this change, see person_repository.py
list_in_clan). To keep this test deterministic and independent of that bug, seeded
ids are assigned in the SAME order as the seeded (zero-padded, lexicographically
sortable) names, so name-order and id-order coincide here.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.person.commands import ListPersons
from app.application.person.handlers import PersonQueryHandler
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.person_repository import SqlAlchemyPersonRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed_persons(session: AsyncSession, count: int) -> tuple[uuid.UUID, list[uuid.UUID]]:
    clan_id, actor = uuid.uuid4(), uuid.uuid4()
    await session.execute(
        sa.text("INSERT INTO clans (id, name, slug, is_active) VALUES (:id, :n, :sl, true)"),
        {"id": clan_id, "n": f"C{clan_id.hex[:6]}", "sl": f"c-{clan_id.hex[:8]}"},
    )
    # ids assigned in the same order as the (lexicographically increasing) names, so
    # id-order and name-order coincide — see module docstring.
    ids = [uuid.UUID(int=i + 1) for i in range(count)]
    for i, pid in enumerate(ids):
        await session.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                "VALUES (:id, :n, 'unknown', :cid, :cb)"
            ),
            {"id": pid, "n": f"Person {i:04d}", "cid": clan_id, "cb": actor},
        )
        await session.execute(
            sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
            {"p": pid, "c": clan_id},
        )
    await session.commit()
    return clan_id, ids


async def test_list_persons_pages_forward_via_cursor(async_session: AsyncSession) -> None:
    limit = 2
    clan_id, seeded_ids = await _seed_persons(async_session, count=5)

    uow = SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    repo = SqlAlchemyPersonRepository(uow)
    handler = PersonQueryHandler(repo)

    page1, meta1 = await handler.list_persons(ListPersons(clan_id=clan_id, limit=limit))
    assert len(page1) == limit
    assert meta1["has_more"] is True
    assert meta1["limit"] == limit
    assert meta1["cursor"] is not None

    page2, meta2 = await handler.list_persons(
        ListPersons(clan_id=clan_id, limit=limit, cursor=meta1["cursor"])
    )
    assert len(page2) == limit
    assert meta2["limit"] == limit

    page1_ids = {p.id for p in page1}
    page2_ids = {p.id for p in page2}
    assert page1_ids.isdisjoint(page2_ids), "page 2 must not repeat a person already on page 1"
    # Forward progress: page 2 picks up where page 1 left off (both orderings agree
    # here, see module docstring), i.e. it covers the next names in sequence.
    assert page1_ids | page2_ids <= set(seeded_ids)
    assert page2_ids != page1_ids
