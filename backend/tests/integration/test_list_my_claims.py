"""ClaimQueryHandler.list_my_claims returns the caller's own claims, filtered + paged."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.person.claim_handlers import ClaimQueryHandler
from app.infrastructure.persistence.claim_repository import SqlAlchemyClaimQueryPort

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _clan(s: AsyncSession) -> uuid.UUID:
    cid = uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sl)"),
        {"id": cid, "sl": f"c-{cid.hex[:8]}"},
    )
    return cid


async def _user(s: AsyncSession) -> uuid.UUID:
    uid = uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'U')"),
        {"id": uid, "e": f"u-{uid.hex[:8]}@ex.com"},
    )
    return uid


async def _person(s: AsyncSession, clan_id: uuid.UUID, creator: uuid.UUID) -> uuid.UUID:
    pid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, 'P', 'male', :c, :cb)"
        ),
        {"id": pid, "c": clan_id, "cb": creator},
    )
    return pid


async def _claim(
    s: AsyncSession, user_id: uuid.UUID, person_id: uuid.UUID, status: str = "PENDING"
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO identity_claims (id, user_id, person_id, status) VALUES (:id, :u, :p, :st)"
        ),
        {"id": uuid.uuid4(), "u": user_id, "p": person_id, "st": status},
    )


async def _seed(async_session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    clan = await _clan(async_session)
    creator = uuid.uuid4()
    user_a, user_b = await _user(async_session), await _user(async_session)
    p1, p2, p3 = (
        await _person(async_session, clan, creator),
        await _person(async_session, clan, creator),
        await _person(async_session, clan, creator),
    )
    await _claim(async_session, user_a, p1, "PENDING")
    await _claim(async_session, user_a, p2, "APPROVED")
    await _claim(async_session, user_b, p3, "PENDING")  # other user's claim
    await async_session.commit()
    return user_a, user_b


async def test_list_my_claims_returns_only_callers_claims(async_session: AsyncSession) -> None:
    user_a, user_b = await _seed(async_session)
    handler = ClaimQueryHandler(SqlAlchemyClaimQueryPort(async_session))

    result = await handler.list_my_claims(user_id=user_a)
    assert result.total == 2
    assert {str(i.user_id) for i in result.items} == {str(user_a)}  # never user_b's

    result_b = await handler.list_my_claims(user_id=user_b)
    assert result_b.total == 1


async def test_list_my_claims_status_filter_and_paging(async_session: AsyncSession) -> None:
    user_a, _ = await _seed(async_session)
    handler = ClaimQueryHandler(SqlAlchemyClaimQueryPort(async_session))

    pending = await handler.list_my_claims(user_id=user_a, status="PENDING")
    assert pending.total == 1 and pending.items[0].status == "PENDING"

    page1 = await handler.list_my_claims(user_id=user_a, page=1, page_size=1)
    assert page1.total == 2 and len(page1.items) == 1  # total counts all, page returns 1
