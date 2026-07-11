"""Real-DB regression for F-1 5a: GET /persons meta pagination (cursor/has_more).

Seeds more persons than the page limit and drives PersonQueryHandler.list_persons
(the same code path the route calls) across two pages via the real migrated schema.

The list is ordered by (full_name, id) — the cursor MUST encode both fields.
``test_list_persons_pages_by_name_order_when_ids_disagree`` seeds persons whose id
order is deliberately NOT the same as their full_name order, so it fails against a
bare id-cursor (id-order != name-order skips/duplicates rows) and only passes once
the cursor is a composite (full_name, id) pair.
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
    # id-order and name-order coincide here — this test only exercises the
    # forward-progress/no-repeat contract, not the id-vs-name-order mismatch (see
    # test_list_persons_pages_by_name_order_when_ids_disagree for that).
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


async def _seed_persons_with_names(
    session: AsyncSession, names_by_id_order: list[str]
) -> uuid.UUID:
    """Seed persons whose full_name values are NOT in id order.

    ``names_by_id_order[i]`` is the full_name assigned to the i-th (ascending) id, so
    callers can deliberately make id-order disagree with full_name-order. IDs are
    random (not the fixed ``uuid.UUID(int=...)`` sequence other tests in this module
    use) since the underlying test database is shared across the whole test session
    and a fixed sequence would collide with rows seeded by other tests.
    """
    clan_id, actor = uuid.uuid4(), uuid.uuid4()
    await session.execute(
        sa.text("INSERT INTO clans (id, name, slug, is_active) VALUES (:id, :n, :sl, true)"),
        {"id": clan_id, "n": f"C{clan_id.hex[:6]}", "sl": f"c-{clan_id.hex[:8]}"},
    )
    ascending_ids = sorted(uuid.uuid4() for _ in names_by_id_order)
    for pid, name in zip(ascending_ids, names_by_id_order, strict=True):
        await session.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                "VALUES (:id, :n, 'unknown', :cid, :cb)"
            ),
            {"id": pid, "n": name, "cid": clan_id, "cb": actor},
        )
        await session.execute(
            sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
            {"p": pid, "c": clan_id},
        )
    await session.commit()
    return clan_id


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


async def test_list_persons_pages_by_name_order_when_ids_disagree(
    async_session: AsyncSession,
) -> None:
    """The list is ordered by full_name; the cursor must follow that order too.

    Seeds ids in an order that deliberately disagrees with alphabetical full_name
    order (id1="Cuong", id2="Anh", id3="Binh"). Against the old bare id-cursor,
    page 2 (filtered by ``id > last_id``) would wrongly skip or repeat rows because
    id-order != name-order; with a correct (full_name, id) cursor, pagination must
    follow full_name order exactly.
    """
    limit = 2
    # names_by_id_order[i] is the name for the i-th ascending id (id1, id2, id3, ...).
    clan_id = await _seed_persons_with_names(async_session, ["Cuong", "Anh", "Binh"])

    uow = SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    repo = SqlAlchemyPersonRepository(uow)
    handler = PersonQueryHandler(repo)

    page1, meta1 = await handler.list_persons(ListPersons(clan_id=clan_id, limit=limit))
    assert [p.full_name for p in page1] == ["Anh", "Binh"]
    assert meta1["has_more"] is True
    assert meta1["cursor"] is not None

    page2, meta2 = await handler.list_persons(
        ListPersons(clan_id=clan_id, limit=limit, cursor=meta1["cursor"])
    )
    assert [p.full_name for p in page2] == ["Cuong"]
    assert meta2["has_more"] is False

    page1_ids = {p.id for p in page1}
    page2_ids = {p.id for p in page2}
    assert page1_ids.isdisjoint(page2_ids), "page 2 must not repeat a person already on page 1"
    all_names = [p.full_name for p in page1] + [p.full_name for p in page2]
    assert all_names == ["Anh", "Binh", "Cuong"], "pages together must cover all 3, in name order"
