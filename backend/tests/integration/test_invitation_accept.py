"""Accepting an invitation creates an approved membership (real DB)."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.invitation.commands import AcceptInvitation
from app.application.invitation.handlers import InvitationCommandHandler
from app.domain.shared.exceptions import ConflictError
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.invitation_repository import SqlAlchemyInvitationRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    async_dsn = migrated_db_url
    engine = create_async_engine(async_dsn)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed_invitation(
    session: AsyncSession,
    *,
    clan_id: uuid.UUID,
    inviter: uuid.UUID,
    token: str,
    email: str = "invitee@example.com",
    status: str = "pending",
) -> None:
    await session.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:6]}"},
    )
    await session.execute(
        sa.text(
            "INSERT INTO clan_invitations (id, clan_id, email, role, invited_by, token, "
            "expires_at, status) VALUES (:id, :c, :e, 'editor', :ib, :t, :exp, :st)"
        ),
        {
            "id": uuid.uuid4(),
            "c": clan_id,
            "e": email,
            "ib": inviter,
            "t": token,
            "exp": datetime.now(UTC) + timedelta(days=7),
            "st": status,
        },
    )


def _handler(session: AsyncSession) -> InvitationCommandHandler:
    return InvitationCommandHandler(
        SqlAlchemyInvitationRepository(session),
        SqlAlchemyUnitOfWork(session, create_event_dispatcher(session)),
    )


async def _accept_audit_count(session: AsyncSession, clan_id: uuid.UUID) -> int:
    return (
        await session.execute(
            sa.text(
                "SELECT count(*) FROM audit_logs "
                "WHERE clan_id = :c AND action = 'invitation.accept'"
            ),
            {"c": clan_id},
        )
    ).scalar() or 0


@pytest.mark.asyncio
async def test_accept_invitation_grants_approved_membership(async_session: AsyncSession) -> None:
    clan_id, inviter, token = uuid.uuid4(), uuid.uuid4(), "tok-accept"
    await async_session.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:6]}"},
    )
    await async_session.execute(
        sa.text(
            "INSERT INTO clan_invitations (id, clan_id, email, role, invited_by, token, "
            "expires_at, status) VALUES (:id, :c, :e, 'editor', :ib, :t, :exp, 'pending')"
        ),
        {
            "id": uuid.uuid4(),
            "c": clan_id,
            "e": "invitee@example.com",
            "ib": inviter,
            "t": token,
            "exp": datetime.now(UTC) + timedelta(days=7),
        },
    )
    await async_session.commit()

    repo = SqlAlchemyInvitationRepository(async_session)
    uow = SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    handler = InvitationCommandHandler(repo, uow)

    invitee = uuid.uuid4()
    out = await handler.accept(
        AcceptInvitation(
            token=token, user_id=invitee, user_email="invitee@example.com", user_full_name="Invitee"
        )
    )
    assert out["role"] == "editor"

    role = await async_session.execute(
        sa.text("SELECT role, is_approved FROM user_clan_roles WHERE user_id = :u"),
        {"u": invitee},
    )
    r = role.first()
    assert r is not None
    assert r.role == "editor" and r.is_approved is True
    inv_status = await async_session.execute(
        sa.text("SELECT status FROM clan_invitations WHERE token = :t"), {"t": token}
    )
    assert inv_status.scalar_one() == "accepted"


@pytest.mark.asyncio
async def test_accept_already_member_reverts_claim_and_writes_no_audit(
    async_session: AsyncSession,
) -> None:
    """A winning CAS that then hits already_member must roll the whole txn back: the
    invitation stays pending and no invitation.accept audit row is written."""
    clan_id, inviter, token = uuid.uuid4(), uuid.uuid4(), "tok-already"
    invitee, email = uuid.uuid4(), f"already-{uuid.uuid4().hex[:8]}@example.com"
    await _seed_invitation(
        async_session, clan_id=clan_id, inviter=inviter, token=token, email=email
    )
    # invitee is ALREADY an approved member of the clan
    await async_session.execute(
        sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'M')"),
        {"id": invitee, "e": email},
    )
    await async_session.execute(
        sa.text(
            "INSERT INTO user_clan_roles (user_id, clan_id, role, is_approved, approved_by, "
            "approved_at) VALUES (:u, :c, 'editor', true, :ib, :at)"
        ),
        {"u": invitee, "c": clan_id, "ib": inviter, "at": datetime.now(UTC)},
    )
    await async_session.commit()

    with pytest.raises(ConflictError, match="already_member"):
        await _handler(async_session).accept(
            AcceptInvitation(token=token, user_id=invitee, user_email=email, user_full_name="M")
        )
    # The request boundary rolls back the uncommitted transaction (the CAS UPDATE).
    await async_session.rollback()

    status = await async_session.execute(
        sa.text("SELECT status FROM clan_invitations WHERE token = :t"), {"t": token}
    )
    assert status.scalar_one() == "pending"  # claim reverted
    assert await _accept_audit_count(async_session, clan_id) == 0  # no event committed


@pytest.mark.asyncio
async def test_accept_non_pending_grants_nothing_and_writes_no_audit(
    async_session: AsyncSession,
) -> None:
    """Accepting an invitation that is no longer pending (e.g. a revoke won the row)
    is a 409 that grants no membership and writes no accept audit row."""
    clan_id, inviter, token = uuid.uuid4(), uuid.uuid4(), "tok-revoked"
    email = f"revoked-{uuid.uuid4().hex[:8]}@example.com"
    await _seed_invitation(
        async_session, clan_id=clan_id, inviter=inviter, token=token, email=email, status="revoked"
    )
    await async_session.commit()

    with pytest.raises(ConflictError, match="not_pending"):
        await _handler(async_session).accept(
            AcceptInvitation(
                token=token, user_id=uuid.uuid4(), user_email=email, user_full_name="X"
            )
        )
    await async_session.rollback()

    assert await _accept_audit_count(async_session, clan_id) == 0
    granted = (
        await async_session.execute(
            sa.text("SELECT count(*) FROM user_clan_roles WHERE clan_id = :c"), {"c": clan_id}
        )
    ).scalar()
    assert granted == 0  # no membership granted
