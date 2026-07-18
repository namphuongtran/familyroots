"""C1: a clan must always keep >= 1 approved admin, even under concurrency.

Covers:
- demoting a *different* admin when two admins exist succeeds (2 -> 1 ok).
- demoting/removing the last admin (any target, not just self) is 403.
- concurrent mutual demotion (A demotes B while B demotes A) must leave
  exactly one admin standing -- `lock_admin_count`'s FOR UPDATE row lock
  serializes the two reducers so the second one re-reads the post-commit
  count instead of racing on a stale read.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from typing import cast

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.v1.clans import list_clan_users, list_pending_users
from app.application.clan.commands import ChangeUserRole, RemoveUser
from app.application.clan.handlers import ClanCommandHandler, ClanQueryHandler
from app.core.permissions import ClanRole
from app.domain.clan.repository import ClanRepository
from app.domain.shared.exceptions import ForbiddenError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.clan_repository import SqlAlchemyClanRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.schemas.clan_membership import ClanUserSummary

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ── raw-SQL seed helpers (mirror tests/integration/test_tenant_isolation.py) ──


async def _add_clan(s: AsyncSession, clan_id: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :sl)"),
        {"id": clan_id, "n": f"C{clan_id.hex[:6]}", "sl": f"c-{clan_id.hex[:8]}"},
    )


async def _add_user_profile(s: AsyncSession, user_id: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, :n)"),
        {"id": user_id, "e": f"user-{user_id.hex[:6]}@example.com", "n": "User"},
    )


async def _add_approved_role(
    s: AsyncSession,
    clan_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    approved_by: uuid.UUID,
) -> None:
    now = datetime.now(UTC)
    await s.execute(
        sa.text(
            "INSERT INTO user_clan_roles "
            "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
            "VALUES (:uid, :cid, :role, true, :approved_by, :approved_at)"
        ),
        {
            "uid": user_id,
            "cid": clan_id,
            "role": role,
            "approved_by": approved_by,
            "approved_at": now,
        },
    )


def make_change_role(
    clan_id: uuid.UUID, *, actor: uuid.UUID, target: uuid.UUID, new_role: str
) -> ChangeUserRole:
    return ChangeUserRole(
        clan_id=clan_id,
        target_user_id=target,
        new_role=new_role,
        actor=ActorInfo(user_id=actor, role="admin"),
    )


def make_remove(clan_id: uuid.UUID, *, actor: uuid.UUID, target: uuid.UUID) -> RemoveUser:
    return RemoveUser(
        clan_id=clan_id,
        target_user_id=target,
        actor=ActorInfo(user_id=actor, role="admin"),
    )


def _make_handler(session: AsyncSession) -> ClanCommandHandler:
    uow = SqlAlchemyUnitOfWork(session, create_event_dispatcher(session))
    # cast: SqlAlchemyClanRepository.list_users' return type is a pre-existing,
    # unrelated mismatch against the ClanRepository port (dict vs tuple) that
    # production code suppresses via a pyproject.toml mypy override on
    # app.infrastructure.dependencies; this test constructs the same handler
    # directly so it needs the same narrow, local suppression.
    return ClanCommandHandler(cast(ClanRepository, SqlAlchemyClanRepository(session)), uow)


class _BarrieredClanRepository(SqlAlchemyClanRepository):
    """Test-only wrapper forcing genuine interleaving at the critical read.

    Plain ``asyncio.gather`` does not guarantee that two independent
    sessions' queries land on the wire at the same instant -- in practice one
    task's chain of awaits (get_user_clan_role -> lock_admin_count -> flush ->
    commit) tends to run to completion well before the other task issues its
    own first query, so the "race" never actually races. Blocking both
    callers on a 2-party ``asyncio.Barrier`` right before the count read
    guarantees both queries are in flight before either has a result, which
    is what actually exercises FOR UPDATE's serialization.
    """

    def __init__(self, session: AsyncSession, barrier: asyncio.Barrier) -> None:
        super().__init__(session)
        self._barrier = barrier

    async def lock_admin_count(self, clan_id: uuid.UUID) -> int:
        await self._barrier.wait()
        return await super().lock_admin_count(clan_id)


# ── fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
def session_maker(
    async_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture()
async def clan_handler_factory(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[Callable[[], ClanCommandHandler]]:
    """Returns a zero-arg callable producing a fresh handler (own session) per call."""
    opened: list[AsyncSession] = []

    def factory() -> ClanCommandHandler:
        session = session_maker()
        opened.append(session)
        return _make_handler(session)

    yield factory

    for s in opened:
        await s.close()


@pytest.fixture()
async def two_admin_clan(
    session_maker: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A clan with exactly two approved admins."""
    clan_id, admin_a, admin_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with session_maker() as s:
        await _add_clan(s, clan_id)
        await _add_user_profile(s, admin_a)
        await _add_user_profile(s, admin_b)
        await _add_approved_role(s, clan_id, admin_a, "admin", admin_a)
        await _add_approved_role(s, clan_id, admin_b, "admin", admin_a)
        await s.commit()
    return clan_id, admin_a, admin_b


@pytest.fixture()
async def one_admin_clan(
    session_maker: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID | None]:
    """A clan with exactly one approved admin."""
    clan_id, admin_a = uuid.uuid4(), uuid.uuid4()
    async with session_maker() as s:
        await _add_clan(s, clan_id)
        await _add_user_profile(s, admin_a)
        await _add_approved_role(s, clan_id, admin_a, "admin", admin_a)
        await s.commit()
    return clan_id, admin_a, None


@pytest.fixture()
async def two_sessions_two_admin_clan(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[tuple[uuid.UUID, ClanCommandHandler, ClanCommandHandler, uuid.UUID, uuid.UUID]]:
    """A clan with two approved admins, plus two INDEPENDENT sessions/handlers."""
    clan_id, admin_a, admin_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with session_maker() as s:
        await _add_clan(s, clan_id)
        await _add_user_profile(s, admin_a)
        await _add_user_profile(s, admin_b)
        await _add_approved_role(s, clan_id, admin_a, "admin", admin_a)
        await _add_approved_role(s, clan_id, admin_b, "admin", admin_a)
        await s.commit()

    session_a = session_maker()
    session_b = session_maker()
    barrier = asyncio.Barrier(2)
    repo_a = _BarrieredClanRepository(session_a, barrier)
    repo_b = _BarrieredClanRepository(session_b, barrier)
    handler_a = ClanCommandHandler(
        cast(ClanRepository, repo_a),
        SqlAlchemyUnitOfWork(session_a, create_event_dispatcher(session_a)),
    )
    handler_b = ClanCommandHandler(
        cast(ClanRepository, repo_b),
        SqlAlchemyUnitOfWork(session_b, create_event_dispatcher(session_b)),
    )
    yield clan_id, handler_a, handler_b, admin_a, admin_b
    await session_a.close()
    await session_b.close()


# ── tests ──────────────────────────────────────────────────────────────────


async def test_demote_other_admin_when_two_exist_succeeds(clan_handler_factory, two_admin_clan):
    clan_id, admin_a, admin_b = two_admin_clan
    handler = clan_handler_factory()
    await handler.change_role(
        make_change_role(clan_id, actor=admin_a, target=admin_b, new_role="viewer")
    )
    # fine: one admin remains


async def test_demote_last_admin_any_target_is_403(clan_handler_factory, one_admin_clan):
    clan_id, admin_a, _other_admin_gone = one_admin_clan
    handler = clan_handler_factory()
    with pytest.raises(ForbiddenError) as exc:
        await handler.change_role(
            make_change_role(clan_id, actor=admin_a, target=admin_a, new_role="editor")
        )
    assert exc.value.code == "clan.last_admin_cannot_demote"


async def test_remove_last_admin_is_403(clan_handler_factory, two_admin_clan):
    clan_id, admin_a, admin_b = two_admin_clan
    handler = clan_handler_factory()
    await handler.remove_user(make_remove(clan_id, actor=admin_a, target=admin_b))  # ok, 2 -> 1
    handler2 = clan_handler_factory()
    with pytest.raises(ForbiddenError) as exc:
        # a (hypothetical) second admin path removing the survivor
        await handler2.remove_user(make_remove(clan_id, actor=admin_b, target=admin_a))
    assert exc.value.code == "clan.last_admin_cannot_remove"


async def test_concurrent_mutual_demotion_leaves_one_admin(
    two_sessions_two_admin_clan, session_maker
):
    """THE race: A demotes B while B demotes A. Exactly one must succeed."""
    clan_id, handler_a, handler_b, admin_a, admin_b = two_sessions_two_admin_clan
    results = await asyncio.gather(
        handler_a.change_role(
            make_change_role(clan_id, actor=admin_a, target=admin_b, new_role="viewer")
        ),
        handler_b.change_role(
            make_change_role(clan_id, actor=admin_b, target=admin_a, new_role="viewer")
        ),
        return_exceptions=True,
    )
    failures = [r for r in results if isinstance(r, Exception)]
    assert (
        len(failures) == 1 and getattr(failures[0], "code", "") == "clan.last_admin_cannot_demote"
    )

    # and the DB still has exactly one approved admin (assert via a fresh session count)
    async with session_maker() as verify:
        result = await verify.execute(
            sa.text(
                "SELECT COUNT(*) FROM user_clan_roles "
                "WHERE clan_id = :cid AND role = 'admin' AND is_approved = true"
            ),
            {"cid": clan_id},
        )
        assert result.scalar_one() == 1


# ── coherence guard: /clans/me/users + /pending wire shape ──────────────────
#
# Drives the actual route functions (as test_clan_users_person_id.py does),
# not a hand-reconstructed dict, so the guard fails if the real wire mapping
# in app/api/v1/clans.py ever drifts from ClanUserSummary.


async def _add_person(s: AsyncSession, clan_id: uuid.UUID, creator: uuid.UUID) -> uuid.UUID:
    person_id = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, 'P', 'male', :c, :cb)"
        ),
        {"id": person_id, "c": clan_id, "cb": creator},
    )
    return person_id


async def _add_linked_user_profile(
    s: AsyncSession, user_id: uuid.UUID, person_id: uuid.UUID | None
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO user_profiles (id, email, display_name, person_id) "
            "VALUES (:id, :e, 'User', :pid)"
        ),
        {"id": user_id, "e": f"user-{user_id.hex[:6]}@example.com", "pid": person_id},
    )


async def _add_pending_role(
    s: AsyncSession, clan_id: uuid.UUID, user_id: uuid.UUID, role: str
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO user_clan_roles (user_id, clan_id, role, is_approved) "
            "VALUES (:u, :c, :r, false)"
        ),
        {"u": user_id, "c": clan_id, "r": role},
    )


def _make_query_handler(session: AsyncSession) -> ClanQueryHandler:
    return ClanQueryHandler(cast(ClanRepository, SqlAlchemyClanRepository(session)))


async def test_clan_users_wire_matches_schemas(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Coherence guard for /clans/me/users + /pending — validate real rows against
    ClanUserSummary (pending now carries person_id too, additive per ADR-024)."""
    clan_id = uuid.uuid4()
    approved_user, pending_user = uuid.uuid4(), uuid.uuid4()
    async with session_maker() as s:
        await _add_clan(s, clan_id)
        person_id = await _add_person(s, clan_id, approved_user)
        await _add_linked_user_profile(s, approved_user, person_id)
        await _add_approved_role(s, clan_id, approved_user, "admin", approved_user)
        pending_person_id = await _add_person(s, clan_id, pending_user)
        await _add_linked_user_profile(s, pending_user, pending_person_id)
        await _add_pending_role(s, clan_id, pending_user, "viewer")
        await s.commit()

    async with session_maker() as s:
        query_handler = _make_query_handler(s)
        approved_page = await list_clan_users(
            current_user={"sub": str(approved_user)},
            clan_id=clan_id,
            query_handler=query_handler,
            role=ClanRole.VIEWER,
            cursor=None,
            limit=20,
        )
        pending_page = await list_pending_users(
            current_user={"sub": str(approved_user)},
            clan_id=clan_id,
            query_handler=query_handler,
            role=ClanRole.ADMIN,
            cursor=None,
            limit=20,
        )

    approved = approved_page["data"]
    pending = pending_page["data"]
    assert approved and pending
    for row in approved:
        ClanUserSummary.model_validate(row)
    for row in pending:
        ClanUserSummary.model_validate(row)
    assert any(row["person_id"] is not None for row in pending), pending
