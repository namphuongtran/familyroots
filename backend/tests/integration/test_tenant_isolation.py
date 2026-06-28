"""End-to-end clan-isolation gate (replaces the empty tests/test_tenant.py stub).

Covers the Phase 1 cross-clan fixes from the 2026-06-28 design review, each
against the real migrated schema:

- C4: relationship create rejects person references outside the acting clan.
- C8: get_current_clan_id refuses a suspended clan for all members.
- C6/C7: the tree functions only traverse edges the active clan owns, so a
  branch reachable only via another clan's edge is not surfaced.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
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
from app.core.security import get_current_clan_id
from app.domain.relationship.validator import RelationshipDomainValidator
from app.domain.shared.exceptions import EntityNotFoundError
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


async def _add_clan(s: AsyncSession, clan_id: uuid.UUID, *, is_active: bool = True) -> None:
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug, is_active) VALUES (:id, :n, :sl, :a)"),
        {"id": clan_id, "n": f"C{clan_id.hex[:6]}", "sl": f"c-{clan_id.hex[:8]}", "a": is_active},
    )


async def _add_person(
    s: AsyncSession, pid: uuid.UUID, clan_id: uuid.UUID, actor: uuid.UUID
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, 'P', 'unknown', :cid, :cb)"
        ),
        {"id": pid, "cid": clan_id, "cb": actor},
    )


async def _add_membership(s: AsyncSession, pid: uuid.UUID, clan_id: uuid.UUID) -> None:
    # role defaults to 'blood'; (person_id, clan_id) is the membership definition.
    await s.execute(
        sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
        {"p": pid, "c": clan_id},
    )


def _handlers(session: AsyncSession) -> tuple[MarriageCommandHandler, ParentChildCommandHandler]:
    uow = SqlAlchemyUnitOfWork(session, create_event_dispatcher(session))
    validator = RelationshipDomainValidator(SqlAlchemyRelationshipQueryPort(session))
    return (
        MarriageCommandHandler(SqlAlchemyMarriageRepository(session), uow, validator),
        ParentChildCommandHandler(SqlAlchemyParentChildRepository(session), uow, validator),
    )


# ── C4: cross-clan write rejected; in-clan write allowed ──────────────────────────
async def test_relationship_create_rejects_cross_clan_person(async_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_a, clan_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    in_a, also_a, in_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        await _add_clan(s, clan_a)
        await _add_clan(s, clan_b)
        for pid, cid in ((in_a, clan_a), (also_a, clan_a), (in_b, clan_b)):
            await _add_person(s, pid, cid, actor)
            await _add_membership(s, pid, cid)
        await s.commit()

        marriage_h, pc_h = _handlers(s)
        editor = ActorInfo.from_jwt({"sub": str(actor)}, "editor")

        # clan A editor referencing clan B's person → rejected (invisible to A).
        with pytest.raises(EntityNotFoundError):
            await marriage_h.create(
                CreateMarriage(person1_id=in_a, person2_id=in_b, clan_id=clan_a, actor=editor)
            )
        with pytest.raises(EntityNotFoundError):
            await pc_h.create(
                CreateParentChild(
                    parent_id=in_a,
                    child_id=in_b,
                    clan_id=clan_a,
                    actor=editor,
                    relationship_type="biological",
                )
            )

        # Both persons in clan A → succeeds.
        result = await marriage_h.create(
            CreateMarriage(person1_id=in_a, person2_id=also_a, clan_id=clan_a, actor=editor)
        )
        assert result.id is not None


# ── C8: suspended clan blocks all members; active clan resolves ───────────────────
async def test_suspended_clan_blocks_access(async_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    user_id, active_clan, suspended_clan = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)

    async with maker() as s:
        await _add_clan(s, active_clan, is_active=True)
        await _add_clan(s, suspended_clan, is_active=False)
        await s.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'U')"),
            {"id": user_id, "e": f"u-{user_id.hex[:8]}@ex.com"},
        )
        for cid in (active_clan, suspended_clan):
            await s.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:u, :c, 'admin', true, :u, :t)"
                ),
                {"u": user_id, "c": cid, "t": now},
            )
        await s.commit()

        current_user = {"sub": str(user_id)}
        # Suspended clan → 403.
        with pytest.raises(HTTPException) as exc:
            await get_current_clan_id(current_user, s, str(suspended_clan))
        assert exc.value.status_code == 403

        # Active clan → resolves normally.
        resolved = await get_current_clan_id(current_user, s, str(active_clan))
        assert resolved == active_clan


# ── C6/C7: tree traversal stops at the active clan's edge boundary ────────────────
async def test_tree_stops_at_clan_edge_boundary(async_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_a, clan_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    gpa, dad, kid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        await _add_clan(s, clan_a)
        await _add_clan(s, clan_b)
        for pid in (gpa, dad):
            await _add_person(s, pid, clan_a, actor)
            await _add_membership(s, pid, clan_a)
        await _add_person(s, kid, clan_b, actor)
        await _add_membership(s, kid, clan_b)
        # gpa->dad owned by clan A; dad->kid owned by clan B.
        for parent, child, owner in ((gpa, dad, clan_a), (dad, kid, clan_b)):
            await s.execute(
                sa.text(
                    "INSERT INTO parent_child "
                    "(id, parent_id, child_id, created_by_clan_id, relationship_type, created_by) "
                    "VALUES (:id, :p, :c, :o, 'biological', :cb)"
                ),
                {"id": uuid.uuid4(), "p": parent, "c": child, "o": owner, "cb": actor},
            )
        await s.commit()

        # Clan A's descendant walk from gpa must stop at dad (kid is reachable only
        # via clan B's edge), so kid's data never leaks into clan A's tree.
        rows = (
            await s.execute(
                sa.text("SELECT person_id FROM public.get_family_tree_flat(:r, :c, 10)"),
                {"r": gpa, "c": clan_a},
            )
        ).all()
        ids = {r.person_id for r in rows}
        assert ids == {gpa, dad}
        assert kid not in ids
