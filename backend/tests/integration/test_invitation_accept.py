"""Accepting an invitation creates an approved membership (real DB)."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.invitation.commands import AcceptInvitation
from app.application.invitation.handlers import InvitationCommandHandler
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
