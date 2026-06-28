"""A soft-deleted relationship edge must not block re-creating the same edge.

Before migration 006 the partial unique indexes did not exclude is_deleted rows, so
re-creating a previously soft-deleted marriage/parent-child raised IntegrityError
(2026-06-28 review). This proves the deleted edge no longer occupies the index.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.application.relationship.commands import CreateMarriage, DeleteMarriage
from app.application.relationship.handlers import MarriageCommandHandler
from app.domain.relationship.validator import RelationshipDomainValidator
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.relationship_repository import (
    SqlAlchemyMarriageRepository,
    SqlAlchemyRelationshipQueryPort,
)
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


async def test_recreate_marriage_after_soft_delete(async_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, actor = uuid.uuid4(), uuid.uuid4()
    p1, p2 = uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sl)"),
            {"id": clan_id, "sl": f"c-{clan_id.hex[:8]}"},
        )
        for pid in (p1, p2):
            await s.execute(
                sa.text(
                    "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                    "VALUES (:id, 'P', 'unknown', :c, :cb)"
                ),
                {"id": pid, "c": clan_id, "cb": actor},
            )
            await s.execute(
                sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
                {"p": pid, "c": clan_id},
            )
        await s.commit()

        editor = ActorInfo.from_jwt({"sub": str(actor)}, "editor")
        handler = MarriageCommandHandler(
            SqlAlchemyMarriageRepository(s),
            SqlAlchemyUnitOfWork(s, create_event_dispatcher(s)),
            RelationshipDomainValidator(SqlAlchemyRelationshipQueryPort(s)),
        )

        first = await handler.create(
            CreateMarriage(person1_id=p1, person2_id=p2, clan_id=clan_id, actor=editor)
        )
        await handler.delete(DeleteMarriage(marriage_id=first.id, clan_id=clan_id, actor=editor))

        # Re-creating the same pair must succeed (the soft-deleted row no longer
        # occupies the unique index) — previously this raised IntegrityError.
        again = await handler.create(
            CreateMarriage(person1_id=p1, person2_id=p2, clan_id=clan_id, actor=editor)
        )
        assert again.id != first.id
