"""ClaimQueryHandler.list_my_claims returns the caller's own claims, filtered + cursor-paged."""

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
    assert set(result.keys()) == {"data", "meta"}
    assert {c["user_id"] for c in result["data"]} == {user_a}  # never user_b's
    assert result["meta"]["has_more"] is False and result["meta"]["limit"] == 20

    result_b = await handler.list_my_claims(user_id=user_b)
    assert len(result_b["data"]) == 1


async def test_list_my_claims_status_filter(async_session: AsyncSession) -> None:
    user_a, _ = await _seed(async_session)
    handler = ClaimQueryHandler(SqlAlchemyClaimQueryPort(async_session))

    pending = await handler.list_my_claims(user_id=user_a, status="PENDING")
    assert len(pending["data"]) == 1
    assert pending["data"][0]["status"] == "PENDING"


async def test_list_my_claims_cursor_paging_advances(async_session: AsyncSession) -> None:
    """Seed 3 claims (> limit=2) for one user: page1 has_more True + cursor, page2 advances."""
    clan = await _clan(async_session)
    creator = uuid.uuid4()
    user = await _user(async_session)
    persons = [await _person(async_session, clan, creator) for _ in range(3)]
    # Only one PENDING claim per user is allowed (uq_identity_claim_user_pending); vary
    # status across the 3 seeded claims so the insert doesn't violate that constraint.
    statuses = ["PENDING", "APPROVED", "REJECTED"]
    for p, st in zip(persons, statuses, strict=True):
        await _claim(async_session, user, p, st)
    await async_session.commit()

    handler = ClaimQueryHandler(SqlAlchemyClaimQueryPort(async_session))

    page1 = await handler.list_my_claims(user_id=user, limit=2)
    assert len(page1["data"]) == 2
    assert page1["meta"]["has_more"] is True
    assert page1["meta"]["cursor"] is not None

    page2 = await handler.list_my_claims(user_id=user, limit=2, cursor=page1["meta"]["cursor"])
    assert len(page2["data"]) == 1
    assert page2["meta"]["has_more"] is False
    assert page2["meta"]["cursor"] is None

    # No overlap between pages, and all 3 claims are covered exactly once.
    ids_page1 = {c["id"] for c in page1["data"]}
    ids_page2 = {c["id"] for c in page2["data"]}
    assert ids_page1.isdisjoint(ids_page2)
    assert len(ids_page1 | ids_page2) == 3
