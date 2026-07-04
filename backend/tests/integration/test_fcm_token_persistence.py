"""C1 regression (seam-review-2026-07-04): FCM token writes must COMMIT.

The bug: FCMTokenHandler had no UnitOfWork and nothing else in the chain
committed, so the INSERT rolled back at session close while the API returned
success. The test writes through the real handler wiring in one session, then
verifies from a SECOND session — a flush-only write cannot pass it.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.application.auth.handlers import FCMTokenHandler
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.auth_repository import SqlAlchemyFCMTokenRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


def _handler(db: AsyncSession) -> FCMTokenHandler:
    # Mirror get_fcm_token_handler in app/infrastructure/dependencies.py.
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return FCMTokenHandler(SqlAlchemyFCMTokenRepository(db), uow)


async def _seed_profile(maker: async_sessionmaker[AsyncSession], user_id: uuid.UUID) -> None:
    async with maker() as s:
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) "
                "VALUES (:id, :em, 'FCM Tester') ON CONFLICT (id) DO NOTHING"
            ),
            {"id": user_id, "em": f"fcm-{user_id.hex[:8]}@example.com"},
        )
        await s.commit()


@pytest.mark.asyncio
async def test_register_token_persists_across_sessions(engine: AsyncEngine) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    user_id = uuid.uuid4()
    token = f"tok-{uuid.uuid4().hex}"
    await _seed_profile(maker, user_id)

    async with maker() as db:  # request session: handler must commit itself
        await _handler(db).register_token(
            user_id=str(user_id), token=token, device_platform="android"
        )

    async with maker() as db:  # fresh session: only committed rows are visible
        n = await db.scalar(
            sa.text("SELECT COUNT(*) FROM user_fcm_tokens WHERE token = :t"), {"t": token}
        )
    assert n == 1, "register_token was rolled back at session close (C1 regression)"


@pytest.mark.asyncio
async def test_remove_token_persists_across_sessions(engine: AsyncEngine) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    user_id = uuid.uuid4()
    token = f"tok-{uuid.uuid4().hex}"
    await _seed_profile(maker, user_id)

    async with maker() as db:
        await _handler(db).register_token(user_id=str(user_id), token=token, device_platform="ios")
    async with maker() as db:
        await _handler(db).remove_token(user_id=str(user_id), token=token)

    async with maker() as db:
        n = await db.scalar(
            sa.text("SELECT COUNT(*) FROM user_fcm_tokens WHERE token = :t"), {"t": token}
        )
    assert n == 0, "remove_token was rolled back at session close (C1 regression)"
