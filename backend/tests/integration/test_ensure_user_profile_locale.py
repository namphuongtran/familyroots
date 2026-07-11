"""ensure_user_profile syncs user_profiles.language from the JWT's preferred_locale."""

import uuid
from collections.abc import AsyncGenerator
from typing import Any, cast

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


def _jwt(user_id: uuid.UUID, locale: str | None) -> dict[str, Any]:
    meta: dict[str, Any] = {"full_name": "L Tester"}
    if locale is not None:
        meta["preferred_locale"] = locale
    return {
        "sub": str(user_id),
        "email": f"loc-{user_id.hex[:8]}@example.com",
        "user_metadata": meta,
    }


async def _language(maker: async_sessionmaker[AsyncSession], user_id: uuid.UUID) -> str | None:
    async with maker() as s:
        return cast(
            "str | None",
            await s.scalar(
                sa.text("SELECT language FROM user_profiles WHERE id = :id"), {"id": user_id}
            ),
        )


@pytest.mark.asyncio
async def test_first_login_sets_language_from_jwt(engine: AsyncEngine) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    uid = uuid.uuid4()
    async with maker() as db:
        await ensure_user_profile(_jwt(uid, "en"), db)
    assert await _language(maker, uid) == "en"


@pytest.mark.asyncio
async def test_refresh_updates_changed_language(engine: AsyncEngine) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    uid = uuid.uuid4()
    async with maker() as db:
        await ensure_user_profile(_jwt(uid, "en"), db)
    async with maker() as db:
        await ensure_user_profile(_jwt(uid, "zh"), db)
    assert await _language(maker, uid) == "zh"


@pytest.mark.asyncio
async def test_unknown_or_absent_locale_defaults_vi(engine: AsyncEngine) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    uid = uuid.uuid4()
    async with maker() as db:
        await ensure_user_profile(_jwt(uid, "de"), db)  # unsupported
    assert await _language(maker, uid) == "vi"
    uid2 = uuid.uuid4()
    async with maker() as db:
        await ensure_user_profile(_jwt(uid2, None), db)  # absent
    assert await _language(maker, uid2) == "vi"
