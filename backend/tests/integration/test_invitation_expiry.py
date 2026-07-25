"""Expired invitations must not block re-invite forever (M11) — real-DB, RED-first.

Design: docs/superpowers/specs/2026-07-25-invitation-expiry-reinvite-design.md

These tests exercise ONLY the EXISTING create path + get_pending_by_email. The bug:
an invitation whose ``expires_at`` has passed stays ``status='pending'`` forever, so
``create`` -> ``get_pending_by_email`` matches it (no expiry filter) and raises
``invitation.pending_exists`` (and the partial unique index would block the re-insert
anyway). Tests assert the DESIRED post-fix behaviour; several are RED today (noted per
test). The direct ``expire_stale_pending`` test belongs to Task 2 (method not yet added).
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.invitation.commands import CreateInvitation
from app.application.invitation.handlers import InvitationCommandHandler
from app.domain.shared.exceptions import ConflictError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.invitation_repository import SqlAlchemyInvitationRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


def _handler(session: AsyncSession) -> InvitationCommandHandler:
    return InvitationCommandHandler(
        SqlAlchemyInvitationRepository(session),
        SqlAlchemyUnitOfWork(session, create_event_dispatcher(session)),
    )


async def _seed_clan(session: AsyncSession, clan_id: uuid.UUID) -> None:
    await session.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:6]}"},
    )


async def _seed_pending(
    session: AsyncSession,
    *,
    clan_id: uuid.UUID,
    inviter: uuid.UUID,
    token: str,
    email: str,
    expires_at: datetime,
    status: str = "pending",
) -> uuid.UUID:
    """Insert one clan_invitations row. Email is stored lowercased to match the
    handler's ``cmd.email.strip().lower()`` normalization."""
    inv_id = uuid.uuid4()
    await session.execute(
        sa.text(
            "INSERT INTO clan_invitations (id, clan_id, email, role, invited_by, token, "
            "expires_at, status) VALUES (:id, :c, :e, 'editor', :ib, :t, :exp, :st)"
        ),
        {
            "id": inv_id,
            "c": clan_id,
            "e": email.lower(),
            "ib": inviter,
            "t": token,
            "exp": expires_at,
            "st": status,
        },
    )
    return inv_id


async def _pending_count(session: AsyncSession, clan_id: uuid.UUID, email: str) -> int:
    return (
        await session.execute(
            sa.text(
                "SELECT count(*) FROM clan_invitations "
                "WHERE clan_id = :c AND email = :e AND status = 'pending'"
            ),
            {"c": clan_id, "e": email.lower()},
        )
    ).scalar() or 0


async def _status_of_token(session: AsyncSession, token: str) -> str:
    row = (
        await session.execute(
            sa.text("SELECT status FROM clan_invitations WHERE token = :t"), {"t": token}
        )
    ).scalar_one()
    return str(row)


def _create_cmd(clan_id: uuid.UUID, email: str, inviter: uuid.UUID) -> CreateInvitation:
    return CreateInvitation(
        clan_id=clan_id,
        email=email,
        role="editor",
        actor=ActorInfo(user_id=inviter, role="admin"),
    )


@pytest.mark.asyncio
async def test_reinvite_after_expiry_succeeds(async_session: AsyncSession) -> None:
    """The bug. A past-expiry pending must be lazily retired so re-invite succeeds.

    RED today: create() raises invitation.pending_exists (get_pending_by_email has no
    expiry filter) / the insert collides on uq_clan_invitations_pending.
    """
    clan_id, inviter = uuid.uuid4(), uuid.uuid4()
    email, old_token = "expired-reinvite@example.com", "tok-old-expired"
    await _seed_clan(async_session, clan_id)
    await _seed_pending(
        async_session,
        clan_id=clan_id,
        inviter=inviter,
        token=old_token,
        email=email,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    await async_session.commit()

    out = await _handler(async_session).create(_create_cmd(clan_id, email, inviter))

    assert out["email"] == email
    assert out["token"] != old_token  # a fresh invite, not the stale one
    # Exactly one LIVE pending for the pair: the new invite.
    assert await _pending_count(async_session, clan_id, email) == 1
    # The stale row was retired to 'expired'.
    assert await _status_of_token(async_session, old_token) == "expired"
    # The new row is the pending one.
    assert await _status_of_token(async_session, out["token"]) == "pending"


@pytest.mark.asyncio
async def test_live_pending_still_blocks(async_session: AsyncSession) -> None:
    """Control (GREEN today): a still-valid pending must never be clobbered."""
    clan_id, inviter = uuid.uuid4(), uuid.uuid4()
    email, live_token = "live-blocks@example.com", "tok-live"
    await _seed_clan(async_session, clan_id)
    await _seed_pending(
        async_session,
        clan_id=clan_id,
        inviter=inviter,
        token=live_token,
        email=email,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    await async_session.commit()

    with pytest.raises(ConflictError, match=r"invitation\.pending_exists"):
        await _handler(async_session).create(_create_cmd(clan_id, email, inviter))
    await async_session.rollback()

    # Still exactly one pending row, and it is the original live invite untouched.
    assert await _pending_count(async_session, clan_id, email) == 1
    assert await _status_of_token(async_session, live_token) == "pending"


@pytest.mark.asyncio
async def test_get_pending_by_email_live_only(async_session: AsyncSession) -> None:
    """Direct-repo (test_invitation_repository pattern): get_pending_by_email must be
    live-only. Future-expiry pending -> row; past-expiry pending -> None.

    RED today for the past-expiry case: the filter has no expiry predicate, so it
    returns the stale row instead of None.
    """
    repo = SqlAlchemyInvitationRepository(async_session)

    # Live pending (clan A) -> returned.
    clan_live, inviter = uuid.uuid4(), uuid.uuid4()
    live_email = "live-lookup@example.com"
    await _seed_clan(async_session, clan_live)
    await _seed_pending(
        async_session,
        clan_id=clan_live,
        inviter=inviter,
        token="tok-live-lookup",
        email=live_email,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )

    # Past-expiry pending (separate clan B / email, to isolate) -> must be None.
    clan_stale = uuid.uuid4()
    stale_email = "stale-lookup@example.com"
    await _seed_clan(async_session, clan_stale)
    await _seed_pending(
        async_session,
        clan_id=clan_stale,
        inviter=inviter,
        token="tok-stale-lookup",
        email=stale_email,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    await async_session.commit()

    assert (await repo.get_pending_by_email(clan_live, live_email)) is not None
    assert (await repo.get_pending_by_email(clan_stale, stale_email)) is None


@pytest.mark.asyncio
async def test_reinvite_isolation_two_sided(async_session: AsyncSession) -> None:
    """Real-DB, two-sided isolation. A past-expiry pending for (clanA, email) and a
    FUTURE pending for (clanB, SAME email): re-inviting clanA succeeds and does NOT
    touch clanB's row.

    RED today for the clanA-succeeds half (create raises pending_exists); the clanB
    side is the isolation control.
    """
    clan_a, clan_b, inviter = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    email = "shared-isolation@example.com"
    b_token = "tok-clanb-live"
    await _seed_clan(async_session, clan_a)
    await _seed_clan(async_session, clan_b)
    await _seed_pending(
        async_session,
        clan_id=clan_a,
        inviter=inviter,
        token="tok-clana-expired",
        email=email,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    await _seed_pending(
        async_session,
        clan_id=clan_b,
        inviter=inviter,
        token=b_token,
        email=email,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    await async_session.commit()

    out = await _handler(async_session).create(_create_cmd(clan_a, email, inviter))
    assert out["email"] == email

    # clanA now has exactly one live pending (the new invite).
    assert await _pending_count(async_session, clan_a, email) == 1
    # clanB is untouched: still exactly one pending, same token.
    assert await _pending_count(async_session, clan_b, email) == 1
    assert await _status_of_token(async_session, b_token) == "pending"


@pytest.mark.asyncio
async def test_expire_stale_pending_targets_only_stale(async_session: AsyncSession) -> None:
    """Direct repo probe (Task 2): expire_stale_pending flips ONLY a past-expiry pending
    row to 'expired'; a future-expiry pending and a non-pending row are untouched."""
    repo = SqlAlchemyInvitationRepository(async_session)
    clan = uuid.uuid4()
    inviter = uuid.uuid4()
    await _seed_clan(async_session, clan)

    stale = await _seed_pending(
        async_session,
        clan_id=clan,
        inviter=inviter,
        token="stale-tok",
        email="stale@example.com",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    await async_session.commit()

    # Past-expiry pending -> exactly one row flipped to 'expired'.
    assert await repo.expire_stale_pending(clan, "stale@example.com") == 1
    await async_session.commit()
    assert await _status_of_token(async_session, "stale-tok") == "expired"

    # Future-expiry pending -> untouched (returns 0).
    await _seed_pending(
        async_session,
        clan_id=clan,
        inviter=inviter,
        token="live-tok",
        email="live@example.com",
        expires_at=datetime.now(UTC) + timedelta(days=3),
    )
    # An already-accepted past-expiry row must also be left alone (status guard).
    await _seed_pending(
        async_session,
        clan_id=clan,
        inviter=inviter,
        token="done-tok",
        email="done@example.com",
        expires_at=datetime.now(UTC) - timedelta(days=2),
        status="accepted",
    )
    await async_session.commit()

    assert await repo.expire_stale_pending(clan, "live@example.com") == 0
    assert await repo.expire_stale_pending(clan, "done@example.com") == 0
    await async_session.commit()
    assert await _status_of_token(async_session, "live-tok") == "pending"
    assert await _status_of_token(async_session, "done-tok") == "accepted"
    # The already-expired stale row is idempotent (no longer pending -> 0 rows).
    assert await repo.expire_stale_pending(clan, "stale@example.com") == 0
    _ = stale
