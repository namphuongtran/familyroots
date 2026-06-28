"""SqlAlchemyInvitationRepository against a real migrated DB."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence.invitation_repository import SqlAlchemyInvitationRepository
from app.models.clan_invitation import ClanInvitation


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    async_dsn = migrated_db_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    engine = create_async_engine(async_dsn)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _clan(session: AsyncSession) -> uuid.UUID:
    cid = uuid.uuid4()
    await session.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :s)"),
        {"id": cid, "n": f"c{cid.hex[:6]}", "s": f"c{cid.hex[:6]}"},
    )
    return cid


@pytest.mark.asyncio
async def test_create_and_fetch_by_token_and_pending(async_session: AsyncSession) -> None:
    repo = SqlAlchemyInvitationRepository(async_session)
    clan_id = await _clan(async_session)
    inv = ClanInvitation(
        clan_id=clan_id,
        email="a@example.com",
        role="viewer",
        invited_by=uuid.uuid4(),
        token="tok-123",
        expires_at=datetime.now(UTC) + timedelta(days=7),
        status="pending",
    )
    repo.add_invitation(inv)
    await async_session.commit()

    assert (await repo.get_by_token("tok-123")) is not None
    assert (await repo.get_pending_by_email(clan_id, "a@example.com")) is not None
    assert (await repo.get_pending_by_email(clan_id, "other@example.com")) is None
    assert len(await repo.list_by_clan(clan_id)) == 1


@pytest.mark.asyncio
async def test_one_pending_per_email_enforced(async_session: AsyncSession) -> None:
    repo = SqlAlchemyInvitationRepository(async_session)
    clan_id = await _clan(async_session)
    for _ in range(2):
        repo.add_invitation(
            ClanInvitation(
                clan_id=clan_id,
                email="dup@example.com",
                role="viewer",
                invited_by=uuid.uuid4(),
                token=f"t-{uuid.uuid4().hex}",
                expires_at=datetime.now(UTC) + timedelta(days=7),
                status="pending",
            )
        )
    with pytest.raises(Exception):  # unique partial index uq_clan_invitations_pending  # noqa: B017
        await async_session.commit()
