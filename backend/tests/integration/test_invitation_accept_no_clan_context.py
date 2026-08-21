"""Accepting an invitation runs with NO clan context — so ``clan_invitations`` must not
carry a clan-isolation policy until someone decides where that path should run.

Seed S-009 asks for RLS on ``clan_invitations`` and ``clan_memberships``. Migration 031
enables it on ``clan_memberships`` only. This test is the reason, and it is written as a
guard rather than as prose so the next agent hits it instead of reading past it.

The chain, at 2026-08-22:

* ``POST /api/v1/invitations/{token}/accept`` (``app/api/v1/invitations.py:89-102``)
  declares ``get_current_user`` and the command handler, and deliberately NOT
  ``get_current_clan_id`` — the invitee is not a member of the clan yet, so there is no
  clan for them to select and no membership check that could pass.
* ``get_invitation_command_handler`` (``app/infrastructure/dependencies.py:336-340``) is
  wired to ``get_db``, the RLS request session, which drops to ``familyroots_app`` on
  every transaction (``app/core/rls.py:63``) whether or not a clan is known.
* ``app.clan_id`` is therefore the empty string, so the migration-027 predicate
  ``clan_id = nullif(current_setting('app.clan_id', true), '')::uuid`` is NULL.
* The first thing ``accept`` does is ``get_by_token``
  (``app/infrastructure/persistence/invitation_repository.py:53-58``) — a lookup with no
  ``clan_id`` predicate, because the token IS the authorization.

Add the policy to that table and the lookup returns zero rows: every accept answers
``invitation.not_found``. The write half fails the same way — ``transition_status``
(``invitation_repository.py:107-127``) would match no row and raise
``invitation.not_pending``. Fixing it means deciding whether the accept path moves to the
privileged ``get_system_db`` session (which also removes RLS from invitation create,
list and revoke, all of which ARE clan-scoped) or whether the table stays uncovered. That
is a posture decision with its own ADR, not a line in a migration.

Negative control (run 2026-08-22): adding ``clan_invitations`` to migration 031's table
list makes this test fail with ``EntityNotFoundError: invitation.not_found``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta

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
from app.core.database import RlsSession
from app.core.rls import set_request_clan_id
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.invitation_repository import SqlAlchemyInvitationRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.fixture(autouse=True)
def _reset_clan_context() -> Generator[None]:
    set_request_clan_id(None)
    yield
    set_request_clan_id(None)


async def test_accept_by_token_succeeds_with_no_clan_selected(engine: AsyncEngine) -> None:
    """The real accept use case, on the real request-session class, with the clan
    ContextVar unset — exactly the state the route is in."""
    clan_id, inviter, invitee = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    token = f"tok-{uuid.uuid4().hex}"
    email = f"{invitee.hex[:12]}@example.com"

    async with engine.begin() as conn:  # privileged seeding, bypasses RLS
        await conn.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
            {"id": clan_id, "s": f"c{clan_id.hex[:10]}"},
        )
        await conn.execute(
            sa.text(
                "INSERT INTO clan_invitations (id, clan_id, email, role, invited_by, token, "
                "expires_at, status) VALUES (:id, :c, :e, 'editor', :ib, :t, :exp, 'pending')"
            ),
            {
                "id": uuid.uuid4(),
                "c": clan_id,
                "e": email,
                "ib": inviter,
                "t": token,
                "exp": datetime.now(UTC) + timedelta(days=7),
            },
        )

    rls = async_sessionmaker(
        engine, sync_session_class=RlsSession, expire_on_commit=False, class_=AsyncSession
    )
    set_request_clan_id(None)
    async with rls() as session:
        # Guard: this really is the non-privileged role with no clan, or the assertion
        # below would prove nothing.
        assert await session.scalar(sa.text("SELECT current_user")) == "familyroots_app"
        assert await session.scalar(sa.text("SELECT current_setting('app.clan_id', true)")) == ""

        handler = InvitationCommandHandler(
            SqlAlchemyInvitationRepository(session),
            SqlAlchemyUnitOfWork(session, create_event_dispatcher(session)),
        )
        out = await handler.accept(
            AcceptInvitation(
                token=token, user_id=invitee, user_email=email, user_full_name="Người được mời"
            )
        )
    assert out["clan_id"] == clan_id
    assert out["role"] == "editor"

    async with engine.connect() as conn:  # privileged: the write really landed
        status = await conn.scalar(
            sa.text("SELECT status FROM clan_invitations WHERE token = :t"), {"t": token}
        )
        approved = await conn.scalar(
            sa.text("SELECT is_approved FROM user_clan_roles WHERE user_id = :u"), {"u": invitee}
        )
    assert status == "accepted"
    assert approved is True


async def test_clan_invitations_is_not_rls_enabled(engine: AsyncEngine) -> None:
    """The state above holds only while the table is uncovered. Pinned explicitly so that
    enabling RLS on ``clan_invitations`` fails HERE, next to the reason, rather than only
    in the coverage set in ``test_rls_activation``."""
    async with engine.connect() as conn:
        enabled = await conn.scalar(
            sa.text("SELECT relrowsecurity FROM pg_class WHERE relname = 'clan_invitations'")
        )
    assert enabled is False, (
        "clan_invitations now has RLS enabled. Read this module's docstring: the "
        "accept-by-token path runs with no clan context, so the policy locks every "
        "invitee out. That change needs an ADR and a decision about which session the "
        "accept path runs on."
    )
