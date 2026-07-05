"""SqlAlchemyInvitationRepository against a real migrated DB."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence.invitation_repository import SqlAlchemyInvitationRepository


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    async_dsn = migrated_db_url
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
    inv_id = uuid.uuid4()
    await repo.create_invitation(
        invitation_id=inv_id,
        clan_id=clan_id,
        email="a@example.com",
        role="viewer",
        invited_by=uuid.uuid4(),
        token="tok-123",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    await async_session.commit()

    # get_by_token now maps the ORM row to the Invitation aggregate.
    loaded = await repo.get_by_token("tok-123")
    assert loaded is not None
    assert loaded.id == inv_id
    assert loaded.email == "a@example.com"
    assert loaded.status == "pending"
    assert (await repo.get_pending_by_email(clan_id, "a@example.com")) is not None
    assert (await repo.get_pending_by_email(clan_id, "other@example.com")) is None
    assert len(await repo.list_by_clan(clan_id)) == 1


@pytest.mark.asyncio
async def test_one_pending_per_email_enforced(async_session: AsyncSession) -> None:
    repo = SqlAlchemyInvitationRepository(async_session)
    clan_id = await _clan(async_session)
    # create_invitation flushes each row, so the second (duplicate pending) trips the
    # unique partial index uq_clan_invitations_pending inside the loop.
    with pytest.raises(Exception):  # noqa: B017
        for _ in range(2):
            await repo.create_invitation(
                invitation_id=uuid.uuid4(),
                clan_id=clan_id,
                email="dup@example.com",
                role="viewer",
                invited_by=uuid.uuid4(),
                token=f"t-{uuid.uuid4().hex}",
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
