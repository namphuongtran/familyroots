"""A clan must not read relationship edges created by another clan (strict isolation).

Both handlers took a repository until seed S-056 (2026-08-22); they now take a
read port, which carries the same clan predicate plus the soft-deleted-endpoint
one. The clan question these two tests ask is unchanged.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.relationship.handlers import MarriageQueryHandler, ParentChildQueryHandler
from app.infrastructure.persistence.relationship_repository import (
    SqlAlchemyMarriageReadPort,
    SqlAlchemyParentChildReadPort,
)


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    async_dsn = migrated_db_url
    engine = create_async_engine(async_dsn)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    for cid, slug in ((clan_a, f"a-{clan_a.hex[:6]}"), (clan_b, f"b-{clan_b.hex[:6]}")):
        await session.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :s)"),
            {"id": cid, "n": slug, "s": slug},
        )
    p1, p2, child = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for pid in (p1, p2, child):
        await session.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                "VALUES (:id, 'P', 'unknown', :cid, :cb)"
            ),
            {"id": pid, "cid": clan_a, "cb": uuid.uuid4()},
        )
    marriage_id, link_id = uuid.uuid4(), uuid.uuid4()
    await session.execute(
        sa.text(
            "INSERT INTO marriages"
            " (id, person1_id, person2_id, created_by_clan_id, status, created_by)"
            " VALUES (:id, :p1, :p2, :cid, 'married', :cb)"
        ),
        {"id": marriage_id, "p1": p1, "p2": p2, "cid": clan_a, "cb": uuid.uuid4()},
    )
    await session.execute(
        sa.text(
            "INSERT INTO parent_child"
            " (id, parent_id, child_id, created_by_clan_id, relationship_type, created_by)"
            " VALUES (:id, :p, :c, :cid, 'biological', :cb)"
        ),
        {"id": link_id, "p": p1, "c": child, "cid": clan_a, "cb": uuid.uuid4()},
    )
    await session.commit()
    return clan_a, clan_b, marriage_id, link_id


@pytest.mark.asyncio
async def test_marriage_not_readable_cross_clan(async_session: AsyncSession) -> None:
    clan_a, clan_b, marriage_id, _ = await _seed(async_session)
    handler = MarriageQueryHandler(SqlAlchemyMarriageReadPort(async_session))
    assert await handler.get_by_id(marriage_id, clan_a) is not None
    assert await handler.get_by_id(marriage_id, clan_b) is None


@pytest.mark.asyncio
async def test_parent_child_not_readable_cross_clan(async_session: AsyncSession) -> None:
    clan_a, clan_b, _, link_id = await _seed(async_session)
    handler = ParentChildQueryHandler(SqlAlchemyParentChildReadPort(async_session))
    assert await handler.get_by_id(link_id, clan_a) is not None
    assert await handler.get_by_id(link_id, clan_b) is None
