"""``PATCH /branches/{id}`` refuses a parent that closes a cycle (#390).

Real Postgres, real handler. Each case reads the outcome twice: the refusal
(``branch_parent_cycle``) and the row re-read afterwards, which must be unchanged.
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

from app.application.branch.handlers import BranchCommandHandler
from app.domain.shared.exceptions import BusinessRuleViolation
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.branch_repository import SqlAlchemyBranchRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


async def _setup(
    engine: AsyncEngine,
) -> tuple[AsyncSession, BranchCommandHandler, uuid.UUID, ActorInfo]:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    s = maker()
    clan = uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sl)"),
        {"id": clan, "sl": f"c-{clan.hex[:8]}"},
    )
    await s.commit()
    uow = SqlAlchemyUnitOfWork(s, create_event_dispatcher(s))
    handler = BranchCommandHandler(SqlAlchemyBranchRepository(uow), uow)
    actor = ActorInfo.from_jwt({"sub": str(uuid.uuid4())}, "editor")
    return s, handler, clan, actor


async def _parent_of(s: AsyncSession, branch_id: uuid.UUID) -> uuid.UUID | None:
    row = await s.execute(
        sa.text("SELECT parent_branch_id FROM branches WHERE id = :i"), {"i": branch_id}
    )
    parent: uuid.UUID | None = row.scalar_one()
    return parent


async def test_two_step_cycle_is_refused_and_row_unchanged(async_engine: AsyncEngine) -> None:
    s, h, clan, actor = await _setup(async_engine)
    async with s:
        a = await h.create(clan_id=clan, actor=actor, name="A")
        b = await h.create(clan_id=clan, actor=actor, name="B", parent_branch_id=a.id)
        with pytest.raises(BusinessRuleViolation) as exc:
            await h.update(
                branch_id=a.id, clan_id=clan, actor=actor, changes={"parent_branch_id": b.id}
            )
        assert exc.value.code == "branch_parent_cycle"
        await s.rollback()
        assert await _parent_of(s, a.id) is None


async def test_three_step_cycle_is_refused_and_row_unchanged(async_engine: AsyncEngine) -> None:
    s, h, clan, actor = await _setup(async_engine)
    async with s:
        a = await h.create(clan_id=clan, actor=actor, name="A")
        b = await h.create(clan_id=clan, actor=actor, name="B", parent_branch_id=a.id)
        c = await h.create(clan_id=clan, actor=actor, name="C", parent_branch_id=b.id)
        with pytest.raises(BusinessRuleViolation) as exc:
            await h.update(
                branch_id=a.id, clan_id=clan, actor=actor, changes={"parent_branch_id": c.id}
            )
        assert exc.value.code == "branch_parent_cycle"
        await s.rollback()
        assert await _parent_of(s, a.id) is None


async def test_non_ancestor_move_and_clearing_still_succeed(async_engine: AsyncEngine) -> None:
    s, h, clan, actor = await _setup(async_engine)
    async with s:
        a = await h.create(clan_id=clan, actor=actor, name="A")
        b = await h.create(clan_id=clan, actor=actor, name="B", parent_branch_id=a.id)
        c = await h.create(clan_id=clan, actor=actor, name="C")
        moved = await h.update(
            branch_id=b.id, clan_id=clan, actor=actor, changes={"parent_branch_id": c.id}
        )
        assert moved.parent_branch_id == c.id
        cleared = await h.update(
            branch_id=b.id, clan_id=clan, actor=actor, changes={"parent_branch_id": None}
        )
        assert cleared.parent_branch_id is None
