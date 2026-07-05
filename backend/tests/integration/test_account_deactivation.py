"""L3: a deactivated account (user_profiles.is_active = False) cannot act.

Deactivation lives only in our DB — the Supabase JWT stays valid — so it must be
enforced on every authenticated, DB-touching path: ensure_user_profile (the profile /
super-admin path) and get_current_clan_id (every clan-scoped endpoint). A revert of
either check lets a deactivated user through and fails these tests.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.exceptions import ForbiddenError
from app.core.security import ensure_user_profile, get_current_clan_id

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed(s: AsyncSession, *, active: bool) -> tuple[uuid.UUID, uuid.UUID]:
    """Create an (active clan, user with an approved membership) and return their ids.

    The user's profile is active/inactive per ``active``.
    """
    clan_id, user_id = uuid.uuid4(), uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:c, 'C', :sl)"),
        {"c": clan_id, "sl": f"c-{clan_id.hex[:8]}"},
    )
    await s.execute(
        sa.text(
            "INSERT INTO user_profiles (id, email, display_name, is_active) "
            "VALUES (:u, :e, 'U', :act)"
        ),
        {"u": user_id, "e": f"u-{user_id.hex[:8]}@ex.com", "act": active},
    )
    await s.execute(
        sa.text(
            "INSERT INTO user_clan_roles (user_id, clan_id, role, is_approved, approved_by, "
            "approved_at) VALUES (:u, :c, 'editor', true, :u, now())"
        ),
        {"u": user_id, "c": clan_id},
    )
    await s.commit()
    return clan_id, user_id


async def test_deactivated_user_blocked_from_clan_scope(async_session: AsyncSession) -> None:
    clan_id, user_id = await _seed(async_session, active=False)
    with pytest.raises(ForbiddenError, match="account_deactivated"):
        await get_current_clan_id(
            current_user={"sub": str(user_id)},
            db=async_session,
            x_current_clan_id=str(clan_id),
        )


async def test_active_user_resolves_clan(async_session: AsyncSession) -> None:
    """Positive control: an active user with the same setup resolves the clan."""
    clan_id, user_id = await _seed(async_session, active=True)
    resolved = await get_current_clan_id(
        current_user={"sub": str(user_id)},
        db=async_session,
        x_current_clan_id=str(clan_id),
    )
    assert resolved == clan_id


async def test_deactivated_user_blocked_at_ensure_profile(async_session: AsyncSession) -> None:
    _, user_id = await _seed(async_session, active=False)
    with pytest.raises(ForbiddenError, match="account_deactivated"):
        await ensure_user_profile(current_user={"sub": str(user_id)}, db=async_session)
