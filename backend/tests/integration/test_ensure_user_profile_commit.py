"""A1 regression (critical-findings-2026-07): ensure_user_profile must COMMIT.

The bug: ensure_user_profile lazily created the local UserProfile row (and
refreshed last_login_at) with db.add()/profile.last_login_at=... + flush()
only. get_db's `async with AsyncSessionLocal()` does not commit on exit, so
on a READ-ONLY request (e.g. any GET gated by get_super_admin, which depends
on ensure_user_profile but performs no other write) the INSERT/UPDATE is
flushed then rolled back at session close — the profile row never persists.
On write requests the handler's own UoW.commit() on the same session
incidentally commits it, masking the bug.

Each test calls ensure_user_profile directly (it's a plain async function
taking `current_user` and `db`) against a real Postgres session, mirroring
the pattern in test_fcm_token_persistence.py (C1, same bug class).
"""

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

from app.core.exceptions import ForbiddenError
from app.core.security import ensure_user_profile


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


def _current_user(user_id: uuid.UUID, email: str, full_name: str = "Test User") -> dict[str, Any]:
    return {
        "sub": str(user_id),
        "email": email,
        "user_metadata": {"full_name": full_name},
    }


@pytest.mark.asyncio
async def test_new_profile_persists_across_sessions(engine: AsyncEngine) -> None:
    """Regression: the profile INSERT must survive session close with no other write."""
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    user_id = uuid.uuid4()
    email = f"a1-{user_id.hex[:8]}@example.com"

    async with maker() as db:  # request session: no other write happens on this session
        await ensure_user_profile(_current_user(user_id, email), db)

    async with maker() as db:  # fresh session: only committed rows are visible
        row = await db.execute(
            sa.text("SELECT last_login_at FROM user_profiles WHERE id = :id"), {"id": user_id}
        )
        result = row.first()

    assert result is not None, "profile INSERT was rolled back at session close (A1 regression)"
    assert result.last_login_at is not None, "last_login_at was not persisted"


@pytest.mark.asyncio
async def test_stale_last_login_update_persists_across_sessions(engine: AsyncEngine) -> None:
    """Regression: the throttled last_login_at UPDATE must also survive session close."""
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    user_id = uuid.uuid4()
    email = f"a1-stale-{user_id.hex[:8]}@example.com"
    stale = datetime.now(UTC) - timedelta(seconds=1000)

    async with maker() as db:
        await db.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name, last_login_at) "
                "VALUES (:id, :em, 'Stale User', :ts)"
            ),
            {"id": user_id, "em": email, "ts": stale},
        )
        await db.commit()

    async with maker() as db:  # request session: no other write happens on this session
        await ensure_user_profile(_current_user(user_id, email), db)

    async with maker() as db:
        row = await db.execute(
            sa.text("SELECT last_login_at FROM user_profiles WHERE id = :id"), {"id": user_id}
        )
        result = row.scalar_one()

    assert result > stale, "throttled last_login_at refresh was rolled back (A1 regression)"


@pytest.mark.asyncio
async def test_idempotent_and_race_safe(engine: AsyncEngine) -> None:
    """Calling twice for the same sub (from different sessions) yields exactly one row,
    with no IntegrityError — the concurrent-first-login race is closed by
    ON CONFLICT (id) DO NOTHING."""
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    user_id = uuid.uuid4()
    email = f"a1-race-{user_id.hex[:8]}@example.com"

    async with maker() as db1:
        await ensure_user_profile(_current_user(user_id, email), db1)

    async with maker() as db2:
        await ensure_user_profile(_current_user(user_id, email), db2)

    async with maker() as db:
        n = await db.scalar(
            sa.text("SELECT COUNT(*) FROM user_profiles WHERE id = :id"), {"id": user_id}
        )
    assert n == 1


@pytest.mark.asyncio
async def test_deactivated_account_still_blocked(engine: AsyncEngine) -> None:
    """A deactivated profile must still raise ForbiddenError('account_deactivated')."""
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    user_id = uuid.uuid4()
    email = f"a1-deactivated-{user_id.hex[:8]}@example.com"

    async with maker() as db:
        await db.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name, is_active) "
                "VALUES (:id, :em, 'Deactivated User', false)"
            ),
            {"id": user_id, "em": email},
        )
        await db.commit()

    async with maker() as db:
        with pytest.raises(ForbiddenError, match="account_deactivated"):
            await ensure_user_profile(_current_user(user_id, email), db)
