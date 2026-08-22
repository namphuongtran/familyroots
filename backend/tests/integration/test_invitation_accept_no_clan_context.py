"""Accepting an invitation runs with NO clan context, so it runs on the SYSTEM session.

This module used to argue the opposite: it pinned ``clan_invitations`` as un-RLS-able and
told the next agent why. That question is now answered. **ADR-048** decided it, migration
``032`` covers the table, and these tests changed sides with it. The chain that forced the
decision is unchanged and is worth keeping, because it is what makes the current wiring
load-bearing rather than arbitrary:

* ``POST /api/v1/invitations/{token}/accept`` (``app/api/v1/invitations.py:95-99``) declares
  ``get_current_user`` and deliberately NOT ``get_current_clan_id`` — the invitee is not a
  member of the clan yet, so there is no clan for them to select and no membership check that
  could pass.
* The RLS seam drops to ``familyroots_app`` and writes ``app.clan_id`` on EVERY transaction
  of a request session (``app/core/rls.py:63-65``), whether or not a clan is known.
* An unset clan makes the migration-027 predicate
  ``clan_id = nullif(current_setting('app.clan_id', true), '')::uuid`` NULL.
* The first thing ``accept`` does is ``get_by_token``
  (``app/infrastructure/persistence/invitation_repository.py:53-58``) — a lookup with no
  ``clan_id`` predicate, because the token IS the authorization. The write half,
  ``transition_status`` (``invitation_repository.py:107-127``), matches by ``id`` and has no
  ``clan_id`` either.

So under the seam, with the policy live, every accept answers ``invitation.not_found``. ADR-048
moved that one route to ``get_invitation_accept_handler``
(``app/infrastructure/dependencies.py:358-362``), which runs on the privileged
``get_system_db``. Create, list and revoke stay on ``get_db`` and are what the policy protects.

The three tests below are the two halves of that plus the pin:

1. accept succeeds on the system session, with the policy enabled — the shipped path;
2. accept on a request session with no clan raises ``invitation.not_found`` — the failure the
   wiring exists to avoid, watched rather than described;
3. ``clan_invitations`` really is RLS-enabled, so test 1 is not passing because the policy is
   absent.

``tests/unit/api/test_invitation_accept_session_wiring.py`` is the cheap guard that the ROUTE
still resolves the right session. This module is the expensive guard that the session choice
still produces the right behaviour against a real policy.
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
from app.domain.shared.exceptions import EntityNotFoundError
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


async def _seed_pending_invitation(engine: AsyncEngine) -> tuple[uuid.UUID, str, str]:
    """One clan with one pending invitation. Returns ``(clan_id, token, email)``.

    Seeded on the privileged connection, which bypasses RLS — otherwise the fixture would be
    testing the policy instead of setting up for it.
    """
    clan_id, inviter, invitee = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    token = f"tok-{uuid.uuid4().hex}"
    email = f"{invitee.hex[:12]}@example.com"
    async with engine.begin() as conn:
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
    return clan_id, token, email


def _handler(session: AsyncSession) -> InvitationCommandHandler:
    return InvitationCommandHandler(
        SqlAlchemyInvitationRepository(session),
        SqlAlchemyUnitOfWork(session, create_event_dispatcher(session)),
    )


async def test_accept_by_token_succeeds_on_the_system_session(engine: AsyncEngine) -> None:
    """The shipped path (ADR-048): the real accept use case on a session with NO RLS seam,
    which is what ``get_system_db`` hands out (``app/core/database.py:86-93``, using
    ``AsyncSessionLocal`` from ``:49-53``, to which the seam is never attached)."""
    clan_id, token, email = await _seed_pending_invitation(engine)
    invitee = uuid.uuid4()

    system = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with system() as session:
        # Guard: this really is the privileged role, or the assertions below prove nothing
        # about which session accept needs.
        assert await session.scalar(sa.text("SELECT current_user")) != "familyroots_app"

        out = await _handler(session).accept(
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


async def test_accept_under_the_rls_seam_with_no_clan_is_locked_out(engine: AsyncEngine) -> None:
    """The failure ADR-048's wiring exists to avoid, watched rather than described.

    Same use case, same data, on ``RlsSession`` with the clan ContextVar unset — exactly the
    state the route would be in if anyone re-pointed the accept handler at ``get_db``.
    """
    _clan_id, token, email = await _seed_pending_invitation(engine)

    rls = async_sessionmaker(
        engine, sync_session_class=RlsSession, expire_on_commit=False, class_=AsyncSession
    )
    set_request_clan_id(None)
    async with rls() as session:
        assert await session.scalar(sa.text("SELECT current_user")) == "familyroots_app"
        assert await session.scalar(sa.text("SELECT current_setting('app.clan_id', true)")) == ""

        with pytest.raises(EntityNotFoundError) as ei:
            await _handler(session).accept(
                AcceptInvitation(
                    token=token,
                    user_id=uuid.uuid4(),
                    user_email=email,
                    user_full_name="Người được mời",
                )
            )
    assert "invitation.not_found" in str(ei.value)

    async with engine.connect() as conn:  # privileged: nothing was granted
        status = await conn.scalar(
            sa.text("SELECT status FROM clan_invitations WHERE token = :t"), {"t": token}
        )
    assert status == "pending"


async def test_clan_invitations_is_rls_enabled(engine: AsyncEngine) -> None:
    """Migration 032. Without this, the success case above would pass for the wrong reason —
    an absent policy looks exactly like a working one from the privileged session."""
    async with engine.connect() as conn:
        enabled = await conn.scalar(
            sa.text("SELECT relrowsecurity FROM pg_class WHERE relname = 'clan_invitations'")
        )
        policies = (
            (
                await conn.execute(
                    sa.text("SELECT policyname FROM pg_policies WHERE tablename = :t"),
                    {"t": "clan_invitations"},
                )
            )
            .scalars()
            .all()
        )
    assert enabled is True, "migration 032 did not enable RLS on clan_invitations"
    assert list(policies) == ["clan_invitations_clan_isolation"], policies
