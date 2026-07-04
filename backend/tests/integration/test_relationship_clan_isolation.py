"""Clan isolation of the relationship validator's duplicate/count checks.

The validator's ``count_bio_parents`` / ``has_active_marriage`` /
``has_parent_child_link`` reads previously filtered only on person ids, so for a
person shared across clans (persons are M:N via clan_memberships) one clan's edges
leaked into another clan's validation — disclosing that a marriage / parent-child
edge exists in another clan and blocking a clan from recording its own edge.

These are two-sided tests against the real migrated schema: each clan sees ONLY its
own edges, can independently record edges for a *shared* person (which also requires
migration 007's clan-scoped unique indexes — before it the second clan's INSERT hit
a raw IntegrityError on the global unique index), while within-clan duplicate/limit
protection still holds. A negative control asserts the leak would reappear if the
clan filter were dropped.
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

from app.application.relationship.commands import CreateMarriage, CreateParentChild
from app.application.relationship.handlers import (
    MarriageCommandHandler,
    ParentChildCommandHandler,
)
from app.domain.relationship.validator import RelationshipDomainValidator
from app.domain.shared.exceptions import ConflictError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.relationship_repository import (
    SqlAlchemyMarriageRepository,
    SqlAlchemyParentChildRepository,
    SqlAlchemyRelationshipQueryPort,
)
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clear_edges(async_engine: AsyncEngine) -> AsyncGenerator[None]:
    """Keep the shared (session-scoped) migrated DB downgrade-safe.

    These tests deliberately commit the *same* edge for a shared person under two
    clans. ``test_migration_round_trip`` later downgrades 007→006 on this same DB,
    recreating the non-clan-scoped unique index that those duplicates would violate.
    Clearing the two edge tables after each test (runs even on assertion failure)
    leaves no cross-clan duplicate behind.
    """
    yield
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as s:
        await s.execute(sa.text("DELETE FROM parent_child"))
        await s.execute(sa.text("DELETE FROM marriages"))
        await s.commit()


async def _add_clan(s: AsyncSession, clan_id: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug, is_active) VALUES (:id, :n, :sl, true)"),
        {"id": clan_id, "n": f"C{clan_id.hex[:6]}", "sl": f"c-{clan_id.hex[:8]}"},
    )


async def _add_person(
    s: AsyncSession, pid: uuid.UUID, clan_id: uuid.UUID, actor: uuid.UUID
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, 'P', 'unknown', :cid, :cb) ON CONFLICT (id) DO NOTHING"
        ),
        {"id": pid, "cid": clan_id, "cb": actor},
    )


async def _add_membership(s: AsyncSession, pid: uuid.UUID, clan_id: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
        {"p": pid, "c": clan_id},
    )


def _handlers(session: AsyncSession) -> tuple[MarriageCommandHandler, ParentChildCommandHandler]:
    uow = SqlAlchemyUnitOfWork(session, create_event_dispatcher(session))
    validator = RelationshipDomainValidator(SqlAlchemyRelationshipQueryPort(session))
    return (
        MarriageCommandHandler(SqlAlchemyMarriageRepository(uow), uow, validator),
        ParentChildCommandHandler(SqlAlchemyParentChildRepository(uow), uow, validator),
    )


async def test_bio_parent_count_is_clan_scoped(async_engine: AsyncEngine) -> None:
    """A shared child's biological-parent limit is counted per clan, not globally."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_a, clan_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    child = uuid.uuid4()  # shared across both clans
    pa1, pa2, pa3, pb = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        await _add_clan(s, clan_a)
        await _add_clan(s, clan_b)
        # child is a member of BOTH clans; each parent belongs to its own clan.
        await _add_person(s, child, clan_a, actor)
        await _add_membership(s, child, clan_a)
        await _add_membership(s, child, clan_b)
        for pid in (pa1, pa2, pa3):
            await _add_person(s, pid, clan_a, actor)
            await _add_membership(s, pid, clan_a)
        await _add_person(s, pb, clan_b, actor)
        await _add_membership(s, pb, clan_b)
        await s.commit()

        _, pc = _handlers(s)
        ed_a = ActorInfo.from_jwt({"sub": str(actor)}, "editor")

        # Clan A fills the child's two biological parents.
        for parent in (pa1, pa2):
            await pc.create(
                CreateParentChild(
                    parent_id=parent,
                    child_id=child,
                    clan_id=clan_a,
                    actor=ed_a,
                    relationship_type="biological",
                )
            )
        # Clan A adding a third biological parent is blocked (within-clan limit).
        with pytest.raises(ConflictError, match="too_many_biological_parents"):
            await pc.create(
                CreateParentChild(
                    parent_id=pa3,
                    child_id=child,
                    clan_id=clan_a,
                    actor=ed_a,
                    relationship_type="biological",
                )
            )

        # Clan B sees NONE of clan A's parent edges for the shared child, so it can
        # record its own biological parent without hitting the (per-clan) limit.
        res, _warn = await pc.create(
            CreateParentChild(
                parent_id=pb,
                child_id=child,
                clan_id=clan_b,
                actor=ActorInfo.from_jwt({"sub": str(actor)}, "editor"),
                relationship_type="biological",
            )
        )
        assert res.id is not None

        # Negative control: the query port itself must return per-clan counts.
        qp = SqlAlchemyRelationshipQueryPort(s)
        assert await qp.count_bio_parents(child, clan_a) == 2
        assert await qp.count_bio_parents(child, clan_b) == 1
        # If the clan filter were dropped this would be 3 — the leak we fixed.


async def test_edge_uniqueness_and_duplicate_checks_are_clan_scoped(
    async_engine: AsyncEngine,
) -> None:
    """Two clans can each record the same real-world edge for shared persons; a
    within-clan repeat is still rejected as a duplicate."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_a, clan_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    x, y = uuid.uuid4(), uuid.uuid4()  # both shared across both clans

    async with maker() as s:
        await _add_clan(s, clan_a)
        await _add_clan(s, clan_b)
        for pid in (x, y):
            await _add_person(s, pid, clan_a, actor)
            await _add_membership(s, pid, clan_a)
            await _add_membership(s, pid, clan_b)
        await s.commit()

        marriage, pc = _handlers(s)
        ed = ActorInfo.from_jwt({"sub": str(actor)}, "editor")

        # Clan A records marriage(X,Y) and parent_child(X→Y).
        await marriage.create(CreateMarriage(person1_id=x, person2_id=y, clan_id=clan_a, actor=ed))
        await pc.create(
            CreateParentChild(
                parent_id=x, child_id=y, clan_id=clan_a, actor=ed, relationship_type="biological"
            )
        )

        # Clan B records the SAME edges for the SAME shared persons — must succeed
        # (independent per-clan edges; also exercises migration 007's clan-scoped
        # unique indexes — a global index would raise IntegrityError here).
        mb = await marriage.create(
            CreateMarriage(person1_id=x, person2_id=y, clan_id=clan_b, actor=ed)
        )
        pcb, _ = await pc.create(
            CreateParentChild(
                parent_id=x, child_id=y, clan_id=clan_b, actor=ed, relationship_type="biological"
            )
        )
        assert mb.id is not None and pcb.id is not None

        # Within-clan duplicates are still rejected (no leak of the *other* clan's
        # edge — the duplicate is detected against clan A's own row).
        with pytest.raises(ConflictError, match="duplicate_marriage"):
            await marriage.create(
                CreateMarriage(person1_id=y, person2_id=x, clan_id=clan_a, actor=ed)
            )
        with pytest.raises(ConflictError, match="duplicate_parent_child"):
            await pc.create(
                CreateParentChild(
                    parent_id=x,
                    child_id=y,
                    clan_id=clan_a,
                    actor=ed,
                    relationship_type="biological",
                )
            )
