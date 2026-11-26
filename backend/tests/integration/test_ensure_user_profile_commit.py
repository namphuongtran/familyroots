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
            sa.text("SELECT last_login_at, is_active FROM user_profiles WHERE id = :id"),
            {"id": user_id},
        )
        result = row.first()

    assert result is not None, "profile INSERT was rolled back at session close (A1 regression)"
    assert result.last_login_at is not None, "last_login_at was not persisted"
    # Lock the Core-default invariant: the pg_insert omits is_active, so a fresh
    # profile must still get is_active=True — otherwise ensure_user_profile's
    # deactivation gate would spuriously reject brand-new users.
    assert result.is_active is True, "is_active default (True) was not applied on insert"


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
async def test_idempotent_across_sequential_calls(engine: AsyncEngine) -> None:
    """Calling twice for the same sub (from different sessions, sequentially) yields
    exactly one row. Note: the second call's opening SELECT finds the row committed
    by the first call, so this only exercises the else/UPDATE branch — it does NOT
    drive the ON CONFLICT DO NOTHING path. See test_concurrent_first_login_is_race_safe
    below for that."""
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
async def test_concurrent_first_login_is_race_safe(engine: AsyncEngine) -> None:
    """Two concurrent first-logins for the same brand-new sub and email must
    neither raise nor leave a second row.

    Both calls start from separate sessions driven with asyncio.gather, so their
    opening SELECTs can interleave. ``ON CONFLICT (id)`` alone only absorbs a
    conflict on the id index; the loser could fail on ``uq_user_profiles_email``
    first. ``ensure_profile_row`` therefore takes a per-id advisory lock, so the
    loser runs after the winner commits.

    Which interleaving happens is not controlled, so this test proves the outcome
    (no exception, exactly one row) for the interleavings the runs happen to hit,
    not for all of them. Sessions are always closed by their context managers and
    exceptions are collected, so a failure cannot leave a transaction open.

    Discrimination check: removing the advisory lock in ``ensure_profile_row``
    makes this fail intermittently with UniqueViolation on uq_user_profiles_email.
    """
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    user_id = uuid.uuid4()
    email = f"a1-concurrent-{user_id.hex[:8]}@example.com"
    current_user = _current_user(user_id, email)

    async def _call() -> None:
        async with maker() as db:
            await ensure_user_profile(current_user, db)

    # return_exceptions lets both sessions' contexts exit before we assert.
    results = await asyncio.gather(_call(), _call(), return_exceptions=True)
    errors = [r for r in results if isinstance(r, BaseException)]

    async with maker() as db:
        n = await db.scalar(
            sa.text("SELECT COUNT(*) FROM user_profiles WHERE id = :id"), {"id": user_id}
        )
    assert errors == []
    assert n == 1


# Deactivation ("account_deactivated") is no longer enforced by ensure_user_profile —
# since the H1 fix (review 2026-07-18) it is a single chokepoint in get_current_user,
# which this direct-call harness bypasses. See tests/integration/test_deactivation_invariant.py
# for the HTTP-level (real dependency chain) coverage of that invariant.


@pytest.mark.asyncio
async def test_leaked_lock_fails_ddl_with_lock_not_available(engine: AsyncEngine) -> None:
    """A transaction left open on user_profiles makes later DDL fail with 55P03.

    Without the fixture's ``lock_timeout`` the ALTER waits forever; the outer
    ``asyncio.wait_for`` turns that hang into a failure of a different kind.
    """
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as holder, maker() as ddl:
        await holder.execute(sa.text("LOCK TABLE user_profiles IN ACCESS SHARE MODE"))
        # ALTER TABLE needs ACCESS EXCLUSIVE, which conflicts with the held lock.
        with pytest.raises(sa.exc.DBAPIError) as exc:
            await asyncio.wait_for(
                ddl.execute(
                    sa.text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS _lt_probe int")
                ),
                timeout=30,
            )
        assert getattr(exc.value.orig, "sqlstate", None) == "55P03"
