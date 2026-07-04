"""C3 regression (seam-review-2026-07-04): invitation transitions are atomic.

Two levels: (1) repo-level — a conditional UPDATE from a second session blocks
on the first session's row lock and returns False after it commits; (2)
handler-level — revoke after a committed accept is a 409 and leaves the
granted membership in place (owner-decided policy), never a silently-revoked
invitation with a live member.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
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

from app.application.invitation.commands import AcceptInvitation, RevokeInvitation
from app.application.invitation.handlers import InvitationCommandHandler
from app.domain.shared.exceptions import ConflictError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.invitation_repository import SqlAlchemyInvitationRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


def _maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _seed(maker: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """Clan + admin profile + a pending invitation; returns ids/token/email."""
    clan_id, admin_id, inv_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    token = f"race-{uuid.uuid4().hex}"
    email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :em, 'Admin')"
            ),
            {"id": admin_id, "em": f"admin-{admin_id.hex[:8]}@example.com"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO clan_invitations "
                "(id, clan_id, email, role, invited_by, token, expires_at, status) "
                "VALUES (:id, :clan, :em, 'viewer', :by, :tok, :exp, 'pending')"
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
        await s.commit()
    return {
        "clan_id": clan_id,
        "admin_id": admin_id,
        "inv_id": inv_id,
        "token": token,
        "email": email,
    }


def _handler(db: AsyncSession) -> InvitationCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return InvitationCommandHandler(SqlAlchemyInvitationRepository(db), uow)


@pytest.mark.asyncio
async def test_conditional_update_blocks_then_misses(engine: AsyncEngine) -> None:
    """Repo level: S2's transition blocks on S1's uncommitted claim, then
    returns False once S1 commits — the row can only move out of pending once."""
    maker = _maker(engine)
    seeded = await _seed(maker)

    async with maker() as s1, maker() as s2:
        repo1, repo2 = SqlAlchemyInvitationRepository(s1), SqlAlchemyInvitationRepository(s2)

        won = await repo1.transition_status(seeded["inv_id"], expected="pending", to="accepted")
        assert won is True  # uncommitted — holds the row lock

        task = asyncio.create_task(
            repo2.transition_status(seeded["inv_id"], expected="pending", to="revoked")
        )
        done, _ = await asyncio.wait({task}, timeout=0.3)
        assert not done, "second transition should block on the row lock"

        await s1.commit()
        lost = await asyncio.wait_for(task, timeout=5)
        assert lost is False, "after the winner commits, the loser must miss"
        await s2.rollback()


@pytest.mark.asyncio
async def test_revoke_after_accept_is_409_and_keeps_membership(engine: AsyncEngine) -> None:
    """Handler level: the exact C3 scenario — before the fix, this revoke
    returned success and overwrote the accepted invitation."""
    maker = _maker(engine)
    seeded = await _seed(maker)
    invitee_id = uuid.uuid4()

    async with maker() as db:
        await _handler(db).accept(
            AcceptInvitation(
                token=seeded["token"],
                user_id=invitee_id,
                user_email=seeded["email"],
                user_full_name="Invitee",
            )
        )

    async with maker() as db:
        with pytest.raises(ConflictError, match=r"invitation\.not_pending"):
            await _handler(db).revoke(
                RevokeInvitation(
                    invitation_id=seeded["inv_id"],
                    clan_id=seeded["clan_id"],
                    actor=ActorInfo(user_id=seeded["admin_id"], role="admin"),
                )
            )

    async with maker() as s:
        status = await s.scalar(
            sa.text("SELECT status FROM clan_invitations WHERE id = :id"),
            {"id": seeded["inv_id"]},
        )
        roles = await s.scalar(
            sa.text(
                "SELECT COUNT(*) FROM user_clan_roles "
                "WHERE user_id = :u AND clan_id = :c AND is_approved = true"
            ),
            {"u": invitee_id, "c": seeded["clan_id"]},
        )
    assert status == "accepted", "revoke must not overwrite an accepted invitation"
    assert roles == 1, "the granted membership stays; removal is member management's job"
