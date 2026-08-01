"""Track-B B2: the pending-member approve/reject write paths must be atomic.

Both ``approve_user`` and ``reject_user`` read the target ``user_clan_roles`` row,
then mutate it (approve = ORM UPDATE, reject = ORM DELETE). With no row lock on that
row, two admins working the pending queue can interleave:

* reject commits its DELETE first  -> approve's later ORM UPDATE matches 0 rows ->
  ``StaleDataError`` escapes ``integrity_error_handler`` (it is NOT an IntegrityError)
  -> a raw 500 to the client.
* approve commits its UPDATE first  -> reject's DELETE still matches the now-approved
  row -> an *approved member is silently removed* plus a misleading ``user.reject``
  audit row for a user who was actually approved.

Neither is acceptable: exactly one of the two must win with a clean domain outcome,
the loser must get a clean 4xx (never a 500), and the DB + audit trail must agree with
the winner. The fix mirrors the invitation ``transition_status`` guard: an atomic
conditional write (``UPDATE/DELETE ... WHERE is_approved = false``) that wins on
exactly one racer; the loser matches 0 rows and re-reads the committed state to raise
a precise 4xx instead of a 0-row ORM mutate (StaleDataError -> 500).

Real Postgres (asyncio.gather across two independent sessions), barrier-forced
interleaving -- same harness as test_last_admin_race.py.
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

from app.application.clan.commands import ApproveUser, RejectUser
from app.application.clan.handlers import ClanCommandHandler
from app.domain.clan.repository import ClanRepository
from app.domain.shared.exceptions import ConflictError, DomainError, EntityNotFoundError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.clan_repository import SqlAlchemyClanRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.models.user_clan_role import UserClanRole

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# (clan_id, approve/reject handler A, handler B, admin actor, pending target)
_PendingClan = tuple[uuid.UUID, ClanCommandHandler, ClanCommandHandler, uuid.UUID, uuid.UUID]


# ── raw-SQL seed helpers (mirror test_last_admin_race.py) ────────────────────


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


async def _add_approved_admin(s: AsyncSession, clan_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO user_clan_roles "
            "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
            "VALUES (:uid, :cid, 'admin', true, :uid, :at)"
        ),
        {"uid": user_id, "cid": clan_id, "at": datetime.now(UTC)},
    )


async def _add_pending_viewer(s: AsyncSession, clan_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO user_clan_roles (user_id, clan_id, role, is_approved) "
            "VALUES (:u, :c, 'viewer', false)"
        ),
        {"u": user_id, "c": clan_id},
    )


def _approve(clan_id: uuid.UUID, *, actor: uuid.UUID, target: uuid.UUID) -> ApproveUser:
    return ApproveUser(
        clan_id=clan_id,
        target_user_id=target,
        actor=ActorInfo(user_id=actor, role="admin"),
    )


def _reject(clan_id: uuid.UUID, *, actor: uuid.UUID, target: uuid.UUID) -> RejectUser:
    return RejectUser(
        clan_id=clan_id,
        target_user_id=target,
        actor=ActorInfo(user_id=actor, role="admin"),
    )


class _BarrieredClanRepository(SqlAlchemyClanRepository):
    """Force genuine interleaving: release both callers only AFTER both have read
    the target row, so both hold the same *pending* snapshot before either commits
    -- that overlap is exactly what triggers the stale-snapshot race (a barrier
    *before* the read lets one handler run read->mutate->commit to completion
    before the other even reads, so the race never materialises).

    One-shot (``_synced``): only the first read of each session syncs on the
    barrier; the loser's post-conflict re-read must not block on the now-spent
    2-party barrier.
    """

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


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
def session_maker(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


def _make_handler(session: AsyncSession, barrier: asyncio.Barrier) -> ClanCommandHandler:
    repo = _BarrieredClanRepository(session, barrier)
    uow = SqlAlchemyUnitOfWork(session, create_event_dispatcher(session))
    # cast: SqlAlchemyClanRepository.list_users' dict-vs-tuple return type is a
    # pre-existing port mismatch suppressed in production via a dependencies.py
    # mypy override; this test wires the handler directly so it needs the same
    # narrow local suppression (identical to test_last_admin_race.py).
    return ClanCommandHandler(cast(ClanRepository, repo), uow)


@pytest.fixture()
async def pending_member_clan(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[_PendingClan]:
    """A clan with one approved admin (actor) and one pending viewer (target),
    plus two INDEPENDENT sessions/handlers sharing an interleaving barrier."""
    clan_id, admin, target = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with session_maker() as s:
        await _add_clan(s, clan_id)
        await _add_user_profile(s, admin)
        await _add_user_profile(s, target)
        await _add_approved_admin(s, clan_id, admin)
        await _add_pending_viewer(s, clan_id, target)
        await s.commit()

    session_a, session_b = session_maker(), session_maker()
    barrier = asyncio.Barrier(2)
    handler_a = _make_handler(session_a, barrier)
    handler_b = _make_handler(session_b, barrier)
    yield clan_id, handler_a, handler_b, admin, target
    await session_a.close()
    await session_b.close()


async def _target_row(
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


# ── tests ────────────────────────────────────────────────────────────────────


async def test_concurrent_approve_vs_reject_is_atomic(
    pending_member_clan: _PendingClan, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    """approve and reject race on the SAME pending row. Exactly one wins cleanly;
    the loser raises a clean DOMAIN error (never StaleDataError / a raw 500); and the
    DB + audit trail agree with the winner (no ghost-removal of an approved member)."""
    clan_id, handler_a, handler_b, admin, target = pending_member_clan
    results = await asyncio.gather(
        handler_a.approve_user(_approve(clan_id, actor=admin, target=target)),
        handler_b.reject_user(_reject(clan_id, actor=admin, target=target)),
        return_exceptions=True,
    )
    approve_res, reject_res = results[0], results[1]

    failures = [r for r in (approve_res, reject_res) if isinstance(r, Exception)]
    # Exactly one clean winner + one clean loser.
    assert len(failures) == 1, (
        f"expected exactly one winner; approve={approve_res!r} reject={reject_res!r}"
    )
    loser = failures[0]
    # The loser must be a modelled domain error, NOT a leaked StaleDataError / 500.
    assert isinstance(loser, DomainError), f"loser leaked a non-domain error: {loser!r}"
    assert isinstance(loser, EntityNotFoundError | ConflictError)

    row = await _target_row(session_maker, clan_id, target)
    if isinstance(approve_res, Exception):
        # reject won -> the pending row is gone, and no approval audit was written.
        assert row is None
        assert await _audit_count(session_maker, clan_id, "user.approve") == 0
        assert await _audit_count(session_maker, clan_id, "user.reject") == 1
    else:
        # approve won -> the member is approved and NOT silently removed by the
        # losing reject; exactly one approval audit, and no bogus rejection audit.
        assert row is not None and row.is_approved is True
        assert await _audit_count(session_maker, clan_id, "user.approve") == 1
        assert await _audit_count(session_maker, clan_id, "user.reject") == 0


async def test_concurrent_double_approve_emits_one_audit(
    pending_member_clan: _PendingClan, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    """Two admins approve the SAME pending user at once. The row must end approved
    with exactly ONE ``user.approve`` audit row (no duplicate audit / lost-update):
    the loser re-reads the committed approval and raises user.already_approved."""
    clan_id, handler_a, handler_b, admin, target = pending_member_clan
    results = await asyncio.gather(
        handler_a.approve_user(_approve(clan_id, actor=admin, target=target)),
        handler_b.approve_user(_approve(clan_id, actor=admin, target=target)),
        return_exceptions=True,
    )

    failures = [r for r in results if isinstance(r, Exception)]
    assert len(failures) == 1, f"expected exactly one approver to win: {results!r}"
    assert isinstance(failures[0], ConflictError)
    assert getattr(failures[0], "code", "") == "user.already_approved"

    row = await _target_row(session_maker, clan_id, target)
    assert row is not None and row.is_approved is True
    assert await _audit_count(session_maker, clan_id, "user.approve") == 1


class _SabotageRepository(SqlAlchemyClanRepository):
    """Runs a one-shot side-effect (committed on a SEPARATE session) in the window
    between approve's read and its conditional write -- to deterministically build
    the reject-then-re-invite triple race without timing luck."""

    def __init__(self, session: AsyncSession, sabotage: Callable[[], Awaitable[None]]) -> None:
        super().__init__(session)
        self._sabotage: Callable[[], Awaitable[None]] | None = sabotage

    async def approve_if_pending(self, ucr_id: uuid.UUID, approved_by: uuid.UUID) -> bool:
        if self._sabotage is not None:
            sabotage, self._sabotage = self._sabotage, None
            await sabotage()
        return await super().approve_if_pending(ucr_id, approved_by)


async def test_approve_after_reject_then_reinvite_is_not_found(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """The triple race: admin A reads pending row X; before A commits, X is rejected
    (deleted) and the user re-requests, inserting a FRESH pending row Y (same user,
    different id). A's approve must resolve by the id it acted on -> user_not_found,
    NOT user.already_approved (Y is still pending), and Y must be left untouched."""
    clan_id, admin, target = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with session_maker() as s:
        await _add_clan(s, clan_id)
        await _add_user_profile(s, admin)
        await _add_user_profile(s, target)
        await _add_approved_admin(s, clan_id, admin)
        await _add_pending_viewer(s, clan_id, target)  # row X
        await s.commit()

    async def sabotage() -> None:
        # Reject X (delete) + user re-requests (fresh pending row Y), committed so
        # A's READ COMMITTED session sees it on its next statement.
        async with session_maker() as saboteur:
            await saboteur.execute(
                sa.text("DELETE FROM user_clan_roles WHERE clan_id = :c AND user_id = :u"),
                {"c": clan_id, "u": target},
            )
            await _add_pending_viewer(saboteur, clan_id, target)  # row Y
            await saboteur.commit()

    session_a = session_maker()
    repo = _SabotageRepository(session_a, sabotage)
    handler = ClanCommandHandler(
        cast(ClanRepository, repo),
        SqlAlchemyUnitOfWork(session_a, create_event_dispatcher(session_a)),
    )
    try:
        with pytest.raises(EntityNotFoundError) as ei:
            await handler.approve_user(_approve(clan_id, actor=admin, target=target))
        assert ei.value.code == "user_not_found"
    finally:
        await session_a.close()

    # Y survived, still pending, and no approval audit was written.
    row = await _target_row(session_maker, clan_id, target)
    assert row is not None and row.is_approved is False
    assert await _audit_count(session_maker, clan_id, "user.approve") == 0
