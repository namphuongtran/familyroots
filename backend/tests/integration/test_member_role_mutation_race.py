"""Track-B B2: the member role-change / removal write paths must be atomic.

Sibling of test_member_approval_race.py for the OTHER two unguarded member-management
writes. ``change_role`` and ``remove_user`` read the target ``user_clan_roles`` row then
mutate it via the ORM (change = attribute UPDATE, remove = session.delete) with no guard
on that row (``lock_admin_count`` only protects the >=1-admin invariant, and only for
admin targets). So for a non-admin target two admins can interleave:

* a concurrent remove/reject deletes the row between change_role's read and its UPDATE
  -> the 0-row ORM UPDATE raises ``StaleDataError`` (not an IntegrityError -> escapes
  integrity_error_handler -> raw 500).
* the same for a second concurrent remove is WORSE: a 0-row ORM DELETE does not even
  raise (SQLAlchemy only warns), so remove_user *silently succeeds* on an
  already-deleted row and writes a phantom ``user.remove`` audit for a no-op.
* two concurrent change_role calls both match (no compare-and-set) -> both succeed ->
  a lost update (last writer wins the role) plus TWO UserRoleChanged audit rows.

The fix mirrors the approve/reject guard: atomic conditional writes keyed on the row id
(``UPDATE ... WHERE id = :id AND role = :expected`` / ``DELETE ... WHERE id = :id``,
``synchronize_session=False``); the loser matches 0 rows and resolves to a precise 4xx
(user_not_found if the row is gone, else clan.role_changed_concurrently) instead of a
0-row ORM mutate.

Real Postgres. The change-vs-remove StaleDataError case is asymmetric (only the
delete-first ordering is bad), so it is reproduced DETERMINISTICALLY by deleting the row
in the window between the handler's read and its write; the lost-update/duplicate-audit
case is reproduced with barrier-forced concurrency.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
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

from app.application.clan.commands import ChangeUserRole, RemoveUser
from app.application.clan.handlers import ClanCommandHandler
from app.domain.clan.repository import ClanRepository
from app.domain.shared.exceptions import ConflictError, DomainError, EntityNotFoundError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.clan_repository import SqlAlchemyClanRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.models.user_clan_role import UserClanRole

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ── raw-SQL seed helpers ──────────────────────────────────────────────────────


async def _add_clan(s: AsyncSession, clan_id: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :sl)"),
        {"id": clan_id, "n": f"C{clan_id.hex[:6]}", "sl": f"c-{clan_id.hex[:8]}"},
    )


async def _add_user_profile(s: AsyncSession, user_id: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'User')"),
        {"id": user_id, "e": f"user-{user_id.hex[:6]}@example.com"},
    )


async def _add_approved_role(
    s: AsyncSession, clan_id: uuid.UUID, user_id: uuid.UUID, role: str
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO user_clan_roles "
            "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
            "VALUES (:uid, :cid, :role, true, :uid, :at)"
        ),
        {"uid": user_id, "cid": clan_id, "role": role, "at": datetime.now(UTC)},
    )


def _change(
    clan_id: uuid.UUID, *, actor: uuid.UUID, target: uuid.UUID, new_role: str
) -> ChangeUserRole:
    return ChangeUserRole(
        clan_id=clan_id,
        target_user_id=target,
        new_role=new_role,
        actor=ActorInfo(user_id=actor, role="admin"),
    )


def _remove(clan_id: uuid.UUID, *, actor: uuid.UUID, target: uuid.UUID) -> RemoveUser:
    return RemoveUser(
        clan_id=clan_id,
        target_user_id=target,
        actor=ActorInfo(user_id=actor, role="admin"),
    )


class _BarrieredClanRepository(SqlAlchemyClanRepository):
    """Release both callers only AFTER both have read the target row (one-shot), so
    they hold the same snapshot before either commits -- see test_member_approval_race.py."""

    def __init__(self, session: AsyncSession, barrier: asyncio.Barrier) -> None:
        super().__init__(session)
        self._barrier = barrier
        self._synced = False

    async def get_user_clan_role(self, *args: object, **kwargs: object) -> UserClanRole | None:
        row = await super().get_user_clan_role(*args, **kwargs)  # type: ignore[arg-type]
        if not self._synced:
            self._synced = True
            await self._barrier.wait()
        return row


class _SabotageClanRepository(SqlAlchemyClanRepository):
    """Runs a one-shot side-effect (committed on a SEPARATE session) in the window
    between the handler's read and its write, to deterministically reproduce the
    delete-first ordering that turns the OLD 0-row ORM mutate into a StaleDataError."""

    def __init__(self, session: AsyncSession, sabotage: Callable[[], Awaitable[None]]) -> None:
        super().__init__(session)
        self._sabotage: Callable[[], Awaitable[None]] | None = sabotage

    async def get_user_clan_role(self, *args: object, **kwargs: object) -> UserClanRole | None:
        row = await super().get_user_clan_role(*args, **kwargs)  # type: ignore[arg-type]
        if self._sabotage is not None:
            sabotage, self._sabotage = self._sabotage, None
            await sabotage()
        return row


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
def session_maker(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_admin_and_member(
    session_maker: async_sessionmaker[AsyncSession], member_role: str
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A clan with an approved admin (actor) and one approved member (target)."""
    clan_id, admin, target = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with session_maker() as s:
        await _add_clan(s, clan_id)
        await _add_user_profile(s, admin)
        await _add_user_profile(s, target)
        await _add_approved_role(s, clan_id, admin, "admin")
        await _add_approved_role(s, clan_id, target, member_role)
        await s.commit()
    return clan_id, admin, target


def _make_barriered_handler(session: AsyncSession, barrier: asyncio.Barrier) -> ClanCommandHandler:
    repo = _BarrieredClanRepository(session, barrier)
    uow = SqlAlchemyUnitOfWork(session, create_event_dispatcher(session))
    # cast: list_users' dict-vs-tuple return type is a pre-existing port mismatch
    # suppressed in production via a dependencies.py mypy override (see
    # test_last_admin_race.py); this test wires the handler directly.
    return ClanCommandHandler(cast(ClanRepository, repo), uow)


async def _role_row(
    session_maker: async_sessionmaker[AsyncSession], clan_id: uuid.UUID, target: uuid.UUID
) -> UserClanRole | None:
    async with session_maker() as s:
        result = await s.execute(
            sa.select(UserClanRole).where(
                UserClanRole.clan_id == clan_id, UserClanRole.user_id == target
            )
        )
        return result.scalar_one_or_none()


async def _audit_count(
    session_maker: async_sessionmaker[AsyncSession], clan_id: uuid.UUID, action: str
) -> int:
    async with session_maker() as s:
        result = await s.execute(
            sa.text("SELECT COUNT(*) FROM audit_logs WHERE clan_id = :c AND action = :a"),
            {"c": clan_id, "a": action},
        )
        return int(result.scalar_one())


# ── tests ─────────────────────────────────────────────────────────────────────


async def test_change_role_after_concurrent_delete_is_not_found(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A concurrent remove/reject deletes the target between change_role's read and its
    write. change_role must report a clean user_not_found, never a StaleDataError -> 500."""
    clan_id, admin, target = await _seed_admin_and_member(session_maker, "viewer")

    async def sabotage() -> None:
        async with session_maker() as saboteur:
            await saboteur.execute(
                sa.text("DELETE FROM user_clan_roles WHERE clan_id = :c AND user_id = :u"),
                {"c": clan_id, "u": target},
            )
            await saboteur.commit()

    session_a = session_maker()
    handler = ClanCommandHandler(
        cast(ClanRepository, _SabotageClanRepository(session_a, sabotage)),
        SqlAlchemyUnitOfWork(session_a, create_event_dispatcher(session_a)),
    )
    try:
        with pytest.raises(DomainError) as ei:
            await handler.change_role(
                _change(clan_id, actor=admin, target=target, new_role="editor")
            )
        assert isinstance(ei.value, EntityNotFoundError)
        assert ei.value.code == "user_not_found"
    finally:
        await session_a.close()

    assert await _role_row(session_maker, clan_id, target) is None
    assert await _audit_count(session_maker, clan_id, "user.change_role") == 0


async def test_remove_after_concurrent_delete_is_not_found(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A concurrent remove deletes the target between this remove's read and its DELETE.
    remove must report a clean user_not_found, never a StaleDataError -> 500."""
    clan_id, admin, target = await _seed_admin_and_member(session_maker, "viewer")

    async def sabotage() -> None:
        async with session_maker() as saboteur:
            await saboteur.execute(
                sa.text("DELETE FROM user_clan_roles WHERE clan_id = :c AND user_id = :u"),
                {"c": clan_id, "u": target},
            )
            await saboteur.commit()

    session_a = session_maker()
    handler = ClanCommandHandler(
        cast(ClanRepository, _SabotageClanRepository(session_a, sabotage)),
        SqlAlchemyUnitOfWork(session_a, create_event_dispatcher(session_a)),
    )
    try:
        with pytest.raises(DomainError) as ei:
            await handler.remove_user(_remove(clan_id, actor=admin, target=target))
        assert isinstance(ei.value, EntityNotFoundError)
        assert ei.value.code == "user_not_found"
    finally:
        await session_a.close()

    assert await _audit_count(session_maker, clan_id, "user.remove") == 0


async def test_concurrent_double_change_role_emits_one_audit(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Two admins change the SAME viewer's role at once (to editor / to admin). Exactly
    one must win (compare-and-set on the read role); the loser gets a clean domain error,
    the DB keeps the winner's role, and exactly ONE UserRoleChanged audit row is written
    (no lost update / duplicate audit)."""
    clan_id, admin, target = await _seed_admin_and_member(session_maker, "viewer")

    session_a, session_b = session_maker(), session_maker()
    barrier = asyncio.Barrier(2)
    handler_a = _make_barriered_handler(session_a, barrier)
    handler_b = _make_barriered_handler(session_b, barrier)
    try:
        results = await asyncio.gather(
            handler_a.change_role(_change(clan_id, actor=admin, target=target, new_role="editor")),
            handler_b.change_role(_change(clan_id, actor=admin, target=target, new_role="admin")),
            return_exceptions=True,
        )
    finally:
        await session_a.close()
        await session_b.close()

    failures = [r for r in results if isinstance(r, Exception)]
    assert len(failures) == 1, f"expected exactly one winner: {results!r}"
    # The loser's row still exists with the winner's role (not deleted), so it is a
    # 409 conflict (compare-and-set on the read role failed), never a 500.
    assert isinstance(failures[0], ConflictError)
    assert getattr(failures[0], "code", "") == "clan.role_changed_concurrently"

    row = await _role_row(session_maker, clan_id, target)
    assert row is not None and row.role in ("editor", "admin")
    assert await _audit_count(session_maker, clan_id, "user.change_role") == 1
