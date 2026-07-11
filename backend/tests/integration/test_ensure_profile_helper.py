"""ensure_profile_row is idempotent + race-safe; both repos delegate to it."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import cast

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence._profile import ensure_profile_row

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _name(s: AsyncSession, uid: uuid.UUID) -> str | None:
    return cast(
        "str | None",
        await s.scalar(
            sa.text("SELECT display_name FROM user_profiles WHERE id = :id"), {"id": uid}
        ),
    )


async def test_ensure_profile_row_idempotent_and_no_clobber(async_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await ensure_profile_row(async_session, uid, "a@ex.com", "First")
    # Second call for the SAME id must not raise and must NOT overwrite display_name.
    await ensure_profile_row(async_session, uid, "a@ex.com", "Second")
    await async_session.commit()

    count = await async_session.scalar(
        sa.text("SELECT COUNT(*) FROM user_profiles WHERE id = :id"), {"id": uid}
    )
    assert count == 1
    assert await _name(async_session, uid) == "First"  # first writer wins


async def test_ensure_profile_row_defaults_display_name_from_email(
    async_session: AsyncSession,
) -> None:
    uid = uuid.uuid4()
    await ensure_profile_row(async_session, uid, "bob@ex.com", None)
    await async_session.commit()
    assert await _name(async_session, uid) == "bob"


async def test_both_repos_delegate(async_session: AsyncSession) -> None:
    from app.infrastructure.persistence.auth_repository import SqlAlchemyAuthRepository
    from app.infrastructure.persistence.invitation_repository import (
        SqlAlchemyInvitationRepository,
    )

    ua, ub = uuid.uuid4(), uuid.uuid4()
    await SqlAlchemyAuthRepository(async_session).ensure_profile(ua, "ua@ex.com", "UA")
    await SqlAlchemyInvitationRepository(async_session).ensure_profile(ub, "ub@ex.com", "UB")
    await async_session.commit()
    assert await _name(async_session, ua) == "UA"
    assert await _name(async_session, ub) == "UB"
