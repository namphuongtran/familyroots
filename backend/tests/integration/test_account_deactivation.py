"""L3: a deactivated account (user_profiles.is_active = False) cannot act.

Since the H1 fix (review 2026-07-18) the gate lives in ONE place —
``get_current_user`` — and is covered over HTTP (real JWT, real routes) by
``test_deactivation_invariant.py``. This file keeps the layer-level behaviors
that remain true of the clan-resolution path itself: an active user resolves
their clan, and a MISSING profile row is reported as the accurate
``no_approved_clan_membership``, never ``account_deactivated``.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.exceptions import ForbiddenError
from app.core.security import get_current_clan_id

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed(s: AsyncSession, *, active: bool) -> tuple[uuid.UUID, uuid.UUID]:
    """Create an (active clan, user with an approved membership) and return their ids."""
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


async def test_active_user_resolves_clan(async_session: AsyncSession) -> None:
    """Positive control: an active user with an approved membership resolves the clan."""
    clan_id, user_id = await _seed(async_session, active=True)
    resolved = await get_current_clan_id(
        current_user={"sub": str(user_id)},
        db=async_session,
        x_current_clan_id=str(clan_id),
    )
    assert resolved == clan_id


async def test_no_profile_is_not_treated_as_deactivated(async_session: AsyncSession) -> None:
    """A user with no profile row must NOT be reported as deactivated — they fall
    through to the accurate no_approved_clan_membership. Only an explicit
    is_active=False (enforced upstream in get_current_user) is a deactivation."""
    with pytest.raises(ForbiddenError, match="no_approved_clan_membership"):
        await get_current_clan_id(
            current_user={"sub": str(uuid.uuid4())},  # never onboarded → no profile
            db=async_session,
            x_current_clan_id=None,
        )
