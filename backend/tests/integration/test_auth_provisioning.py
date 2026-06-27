"""Registration must provision a user_profiles row before inserting a membership
(regression for the FK violation where UserClanRole referenced a missing profile)."""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.auth.handlers import AuthCommandHandler
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.auth_repository import SqlAlchemyAuthRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture()
async def async_session(migrated_db_url):
    # migrated_db_url is a sync (psycopg2) DSN from the integration conftest;
    # convert to the asyncpg driver for the app's async session.
    async_dsn = migrated_db_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    engine = create_async_engine(async_dsn)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_create_clan_provisions_profile(async_session: AsyncSession):
    repo = SqlAlchemyAuthRepository(async_session)
    uow = SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    handler = AuthCommandHandler(repo, uow)

    user_id = uuid.uuid4()
    slug = f"clan-{user_id.hex[:8]}"

    resp = await handler._assign_clan_membership(
        user_id=user_id,
        email=f"{user_id.hex[:8]}@example.com",
        full_name="Người Dùng",
        clan_action="create",
        clan_name="Họ Nguyễn",
        clan_slug=slug,
    )

    assert resp.is_approved is True

    # A profile row now exists, and the membership row was inserted (no FK error).
    prof = await async_session.execute(
        sa.text("SELECT id FROM user_profiles WHERE id = :id"), {"id": user_id}
    )
    assert prof.scalar_one() == user_id
    role = await async_session.execute(
        sa.text("SELECT role FROM user_clan_roles WHERE user_id = :id"), {"id": user_id}
    )
    assert role.scalar_one() == "admin"


@pytest.mark.asyncio
async def test_register_join_clan_provisions_profile(async_session: AsyncSession):
    repo = SqlAlchemyAuthRepository(async_session)
    uow = SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    handler = AuthCommandHandler(repo, uow)

    # An admin creates a clan to join.
    admin_id = uuid.uuid4()
    slug = f"clan-{admin_id.hex[:8]}"
    created = await handler._assign_clan_membership(
        user_id=admin_id,
        email=f"{admin_id.hex[:8]}@example.com",
        full_name="Admin",
        clan_action="create",
        clan_name="Họ Trần",
        clan_slug=slug,
    )
    clan_id = created.clan_id

    # A second user joins it (pending approval).
    joiner_id = uuid.uuid4()
    resp = await handler._assign_clan_membership(
        user_id=joiner_id,
        email=f"{joiner_id.hex[:8]}@example.com",
        full_name="Thành Viên",
        clan_action="join",
        clan_id=clan_id,
    )
    assert resp.is_approved is False

    prof = await async_session.execute(
        sa.text("SELECT id FROM user_profiles WHERE id = :id"), {"id": joiner_id}
    )
    assert prof.scalar_one() == joiner_id
    role = await async_session.execute(
        sa.text("SELECT role, is_approved FROM user_clan_roles WHERE user_id = :id"),
        {"id": joiner_id},
    )
    row = role.first()
    assert row.role == "viewer"
    assert row.is_approved is False
