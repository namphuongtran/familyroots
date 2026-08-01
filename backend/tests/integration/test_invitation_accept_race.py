"""Track-B B2: accepting an invitation must survive a concurrent membership mutation.

InvitationCommandHandler.accept, after winning the invitation's transition_status
claim, reads the user's existing (pending self-request) user_clan_roles row and — in
the promote branch — mutated it via the ORM (``existing.is_approved = True`` ...). With
no guard on that row, an admin who concurrently rejects/removes the pending self-request
in the window between accept's read and its commit-flush makes that a 0-row ORM UPDATE
-> ``StaleDataError`` (not an IntegrityError, so it escapes integrity_error_handler) ->
raw 500, and the whole accept (invitation included) rolls back — the invitee sees a 500
for a perfectly valid invitation.

The fix mirrors #111/#112: promote the pending row with an atomic conditional UPDATE
keyed on the row id; on a 0-row loss, re-resolve by the exact id (identity-map-immune)
-> the pending row was removed => grant a fresh approved membership (the invitation is
valid); it was approved concurrently => invitation.already_member. Never a 0-row ORM
mutate.

Real Postgres. The bad ordering (delete lands between accept's read and its write) is
reproduced DETERMINISTICALLY by mutating the row inside accept's ``get_user_role`` seam,
committed on a separate session.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.application.invitation.commands import AcceptInvitation
from app.application.invitation.handlers import InvitationCommandHandler
from app.domain.shared.exceptions import ConflictError, DomainError
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.invitation_repository import SqlAlchemyInvitationRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.models.user_clan_role import UserClanRole

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


def _maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _seed(maker: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """Clan + admin (inviter) + invitee profile + a PENDING invitation (role=editor)
    for the invitee AND a PENDING self-request user_clan_roles row (role=viewer)."""
    clan_id, admin_id, invitee_id, inv_id = (uuid.uuid4() for _ in range(4))
    token = f"acc-{uuid.uuid4().hex}"
    email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :em, 'A')"),
            {"id": admin_id, "em": f"admin-{admin_id.hex[:8]}@example.com"},
        )
        await s.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :em, 'I')"),
            {"id": invitee_id, "em": email},
        )
        await s.execute(
            sa.text(
                "INSERT INTO clan_invitations "
                "(id, clan_id, email, role, invited_by, token, expires_at, status) "
                "VALUES (:id, :clan, :em, 'editor', :by, :tok, :exp, 'pending')"
            ),
            {
                "id": inv_id,
                "clan": clan_id,
                "em": email,
                "by": admin_id,
                "tok": token,
                "exp": datetime.now(UTC) + timedelta(days=7),
            },
        )
        # the invitee's pending self-request (what an admin might reject/approve)
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles (user_id, clan_id, role, is_approved) "
                "VALUES (:u, :c, 'viewer', false)"
            ),
            {"u": invitee_id, "c": clan_id},
        )
        await s.commit()
    return {
        "clan_id": clan_id,
        "admin_id": admin_id,
        "invitee_id": invitee_id,
        "inv_id": inv_id,
        "token": token,
        "email": email,
    }


class _SabotageInvitationRepository(SqlAlchemyInvitationRepository):
    """Runs a one-shot side-effect (committed on a SEPARATE session) right after
    accept reads the user's role — i.e. in the window between that read and accept's
    commit-flush — to deterministically reproduce the concurrent-mutation race."""

    def __init__(self, session: AsyncSession, sabotage: Callable[[], Awaitable[None]]) -> None:
        super().__init__(session)
        self._sabotage: Callable[[], Awaitable[None]] | None = sabotage

    async def get_user_role(self, user_id: uuid.UUID, clan_id: uuid.UUID) -> UserClanRole | None:
        row = await super().get_user_role(user_id, clan_id)
        if self._sabotage is not None:
            sabotage, self._sabotage = self._sabotage, None
            await sabotage()
        return row


def _handler(db: AsyncSession, sabotage: Callable[[], Awaitable[None]]) -> InvitationCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return InvitationCommandHandler(_SabotageInvitationRepository(db, sabotage), uow)


def _accept(seeded: dict[str, Any]) -> AcceptInvitation:
    return AcceptInvitation(
        token=seeded["token"],
        user_id=seeded["invitee_id"],
        user_email=seeded["email"],
        user_full_name="Invitee",
    )


async def _membership(
    maker: async_sessionmaker[AsyncSession], seeded: dict[str, Any]
) -> UserClanRole | None:
    async with maker() as s:
        result = await s.execute(
            sa.select(UserClanRole).where(
                UserClanRole.user_id == seeded["invitee_id"],
                UserClanRole.clan_id == seeded["clan_id"],
            )
        )
        return result.scalar_one_or_none()


async def _inv_status(
    maker: async_sessionmaker[AsyncSession], seeded: dict[str, Any]
) -> str | None:
    async with maker() as s:
        status = await s.scalar(
            sa.text("SELECT status FROM clan_invitations WHERE id = :id"), {"id": seeded["inv_id"]}
        )
        return str(status) if status is not None else None


async def test_accept_survives_concurrent_removal_of_pending_request(engine: AsyncEngine) -> None:
    """An admin rejects/removes the invitee's pending self-request between accept's read
    and its write. accept must still grant the invited membership (the invitation is
    valid) -- never a StaleDataError -> 500 -- and the invitation ends accepted."""
    maker = _maker(engine)
    seeded = await _seed(maker)

    async def sabotage() -> None:
        async with maker() as saboteur:
            await saboteur.execute(
                sa.text("DELETE FROM user_clan_roles WHERE user_id = :u AND clan_id = :c"),
                {"u": seeded["invitee_id"], "c": seeded["clan_id"]},
            )
            await saboteur.commit()

    async with maker() as db:
        result = await _handler(db, sabotage).accept(_accept(seeded))

    assert result == {"clan_id": seeded["clan_id"], "role": "editor"}
    row = await _membership(maker, seeded)
    assert row is not None and row.is_approved is True and row.role == "editor"
    assert await _inv_status(maker, seeded) == "accepted"


async def test_accept_after_concurrent_approval_is_already_member(engine: AsyncEngine) -> None:
    """The invitee's pending self-request is APPROVED (as viewer) by an admin between
    accept's read and its write. accept must report invitation.already_member -- and must
    NOT clobber the concurrent approval (the row stays viewer) -- never a 500, and the
    invitation stays pending (the accept transaction rolls back)."""
    maker = _maker(engine)
    seeded = await _seed(maker)

    async def sabotage() -> None:
        async with maker() as saboteur:
            await saboteur.execute(
                sa.text(
                    "UPDATE user_clan_roles SET is_approved = true, approved_by = :by, "
                    "approved_at = now() WHERE user_id = :u AND clan_id = :c"
                ),
                {"by": seeded["admin_id"], "u": seeded["invitee_id"], "c": seeded["clan_id"]},
            )
            await saboteur.commit()

    async with maker() as db:
        with pytest.raises(DomainError) as ei:
            await _handler(db, sabotage).accept(_accept(seeded))
        assert isinstance(ei.value, ConflictError)
        assert ei.value.code == "invitation.already_member"

    row = await _membership(maker, seeded)
    assert row is not None and row.is_approved is True and row.role == "viewer"
    assert await _inv_status(maker, seeded) == "pending"
