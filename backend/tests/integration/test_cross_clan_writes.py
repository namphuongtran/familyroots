"""Branch and event writes must reject body-supplied references outside the clan.

Addresses the C4-sibling write holes flagged in pre-merge review: branch
create/update accepted cross-clan parent_branch_id / founder_person_id, and event
create/update accepted a cross-clan person_id. All now validate against the same
"member of clan_memberships" rule used for relationships.
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

from app.application.branch.handlers import BranchCommandHandler
from app.application.event.handlers import EventCommandHandler
from app.domain.shared.exceptions import EntityNotFoundError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.branch_repository import SqlAlchemyBranchRepository
from app.infrastructure.persistence.event_repository import SqlAlchemyEventRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


async def _clan(s: AsyncSession, cid: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sl)"),
        {"id": cid, "sl": f"c-{cid.hex[:8]}"},
    )


async def _member(s: AsyncSession, pid: uuid.UUID, cid: uuid.UUID, actor: uuid.UUID) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, 'P', 'unknown', :c, :cb)"
        ),
        {"id": pid, "c": cid, "cb": actor},
    )
    await s.execute(
        sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
        {"p": pid, "c": cid},
    )


def _editor(actor: uuid.UUID) -> ActorInfo:
    return ActorInfo.from_jwt({"sub": str(actor)}, "editor")


async def test_branch_rejects_cross_clan_founder(async_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_a, clan_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    in_a, in_b = uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        await _clan(s, clan_a)
        await _clan(s, clan_b)
        await _member(s, in_a, clan_a, actor)
        await _member(s, in_b, clan_b, actor)
        await s.commit()

        h = BranchCommandHandler(
            SqlAlchemyBranchRepository(s), SqlAlchemyUnitOfWork(s, create_event_dispatcher(s))
        )
        # Founder belongs to clan B → rejected for clan A.
        with pytest.raises(EntityNotFoundError):
            await h.create(clan_id=clan_a, actor=_editor(actor), name="B", founder_person_id=in_b)

        # In-clan founder → succeeds; then an update pointing the parent at a
        # non-existent (cross-clan) branch is rejected.
        ok = await h.create(
            clan_id=clan_a, actor=_editor(actor), name="Root", founder_person_id=in_a
        )
        with pytest.raises(EntityNotFoundError):
            await h.update(
                branch_id=ok.id,
                clan_id=clan_a,
                actor=_editor(actor),
                changes={"parent_branch_id": uuid.uuid4()},
            )


async def test_event_rejects_cross_clan_person(async_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_a, clan_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    in_a, in_b = uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        await _clan(s, clan_a)
        await _clan(s, clan_b)
        await _member(s, in_a, clan_a, actor)
        await _member(s, in_b, clan_b, actor)
        await s.commit()

        h = EventCommandHandler(
            SqlAlchemyEventRepository(s), SqlAlchemyUnitOfWork(s, create_event_dispatcher(s))
        )

        async def _create(person_id: uuid.UUID) -> object:
            return await h.create(
                clan_id=clan_a,
                actor=_editor(actor),
                person_id=person_id,
                event_type="custom",
                title="T",
                description=None,
                event_date=date(2026, 1, 1),
                is_lunar_calendar=False,
                is_recurring=False,
                notify_days_before=None,
            )

        # person_id from clan B → rejected for clan A.
        with pytest.raises(EntityNotFoundError):
            await _create(in_b)

        # In-clan person → succeeds.
        result = await _create(in_a)
        assert result.id is not None  # type: ignore[attr-defined]
