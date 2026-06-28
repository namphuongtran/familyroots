"""Person marriage/parent-child projections must only surface edges of the active clan."""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence.person_query_port import SqlAlchemyPersonQueryPort


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    async_dsn = migrated_db_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    engine = create_async_engine(async_dsn)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_marriages_scoped_to_clan(async_session: AsyncSession) -> None:
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    for cid, s in ((clan_a, f"a-{clan_a.hex[:6]}"), (clan_b, f"b-{clan_b.hex[:6]}")):
        await async_session.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :s)"),
            {"id": cid, "n": s, "s": s},
        )
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    for pid in (p1, p2):
        await async_session.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                "VALUES (:id, 'P', 'unknown', :cid, :cb)"
            ),
            {"id": pid, "cid": clan_a, "cb": uuid.uuid4()},
        )
    # Marriage edge owned by clan_b but referencing clan_a's person p1.
    await async_session.execute(
        sa.text(
            "INSERT INTO marriages"
            " (id, person1_id, person2_id, created_by_clan_id, status, created_by)"
            " VALUES (:id, :p1, :p2, :cid, 'married', :cb)"
        ),
        {"id": uuid.uuid4(), "p1": p1, "p2": p2, "cid": clan_b, "cb": uuid.uuid4()},
    )
    await async_session.commit()

    port = SqlAlchemyPersonQueryPort(async_session)
    assert await port.get_marriages(clan_a, p1) == []  # clan_a must not see clan_b's edge
    assert len(await port.get_marriages(clan_b, p1)) == 1


@pytest.mark.asyncio
async def test_get_parent_child_links_scoped_to_clan(async_session: AsyncSession) -> None:
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    for cid, s in ((clan_a, f"a-{clan_a.hex[:6]}"), (clan_b, f"b-{clan_b.hex[:6]}")):
        await async_session.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :s)"),
            {"id": cid, "n": s, "s": s},
        )
    parent, child = uuid.uuid4(), uuid.uuid4()
    for pid in (parent, child):
        await async_session.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                "VALUES (:id, 'P', 'unknown', :cid, :cb)"
            ),
            {"id": pid, "cid": clan_a, "cb": uuid.uuid4()},
        )
    # Parent-child edge owned by clan_b but referencing clan_a's persons.
    await async_session.execute(
        sa.text(
            "INSERT INTO parent_child"
            " (id, parent_id, child_id, created_by_clan_id, relationship_type, created_by)"
            " VALUES (:id, :p, :c, :cid, 'biological', :cb)"
        ),
        {"id": uuid.uuid4(), "p": parent, "c": child, "cid": clan_b, "cb": uuid.uuid4()},
    )
    await async_session.commit()

    port = SqlAlchemyPersonQueryPort(async_session)
    # clan_a must not see clan_b's edge
    assert await port.get_parent_child_links(clan_a, parent) == []
    assert len(await port.get_parent_child_links(clan_b, parent)) == 1
