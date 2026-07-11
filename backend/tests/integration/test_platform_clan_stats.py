"""platform_admin get_clan_detail stats: total_users must not be coupled to member count."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence.platform_admin_query_port import (
    SqlAlchemyPlatformAdminQueryPort,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _clan(s: AsyncSession, cid: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sl)"),
        {"id": cid, "sl": f"c-{cid.hex[:8]}"},
    )


async def _profile(s: AsyncSession, uid: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'U')"),
        {"id": uid, "e": f"u-{uid.hex[:8]}@ex.com"},
    )


async def _role(s: AsyncSession, uid: uuid.UUID, cid: uuid.UUID) -> None:
    now = datetime.now(UTC)
    await s.execute(
        sa.text(
            "INSERT INTO user_clan_roles "
            "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
            "VALUES (:u, :c, 'admin', true, :u, :at)"
        ),
        {"u": uid, "c": cid, "at": now},
    )


async def _person_member(
    s: AsyncSession, clan_id: uuid.UUID, creator: uuid.UUID, *, deleted: bool = False
) -> uuid.UUID:
    pid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by, "
            " is_deleted) VALUES (:id, 'P', 'male', :c, :cb, :d)"
        ),
        {"id": pid, "c": clan_id, "cb": creator, "d": deleted},
    )
    await s.execute(
        sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
        {"p": pid, "c": clan_id},
    )
    return pid


async def test_total_users_counted_when_clan_has_no_persons(async_session: AsyncSession) -> None:
    """The regression: users with roles but zero person-memberships must still count."""
    clan_id = uuid.uuid4()
    await _clan(async_session, clan_id)
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    for u in (u1, u2):
        await _profile(async_session, u)
        await _role(async_session, u, clan_id)
    await async_session.commit()

    detail = await SqlAlchemyPlatformAdminQueryPort(async_session).get_clan_detail(clan_id)
    assert detail.stats.total_users == 2  # was 0 before the fix (no memberships → no rows)
    assert detail.stats.total_members == 0


async def test_members_exclude_soft_deleted_and_users_independent(
    async_session: AsyncSession,
) -> None:
    clan_id, creator = uuid.uuid4(), uuid.uuid4()
    await _clan(async_session, clan_id)
    await _person_member(async_session, clan_id, creator)  # live
    await _person_member(async_session, clan_id, creator)  # live
    await _person_member(async_session, clan_id, creator, deleted=True)  # excluded
    u1, u2, u3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for u in (u1, u2, u3):
        await _profile(async_session, u)
        await _role(async_session, u, clan_id)
    await async_session.commit()

    detail = await SqlAlchemyPlatformAdminQueryPort(async_session).get_clan_detail(clan_id)
    assert detail.stats.total_members == 2  # soft-deleted person excluded
    assert detail.stats.total_users == 3


async def test_clan_stats_isolated_from_other_clan(async_session: AsyncSession) -> None:
    clan_a, clan_b, creator = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _clan(async_session, clan_a)
    await _clan(async_session, clan_b)
    await _person_member(async_session, clan_a, creator)
    ua, ub = uuid.uuid4(), uuid.uuid4()
    await _profile(async_session, ua)
    await _profile(async_session, ub)
    await _role(async_session, ua, clan_a)
    await _role(async_session, ub, clan_b)  # clan B's user must not count for clan A
    # clan B also gets 2 persons
    await _person_member(async_session, clan_b, creator)
    await _person_member(async_session, clan_b, creator)
    await async_session.commit()

    port = SqlAlchemyPlatformAdminQueryPort(async_session)
    a = await port.get_clan_detail(clan_a)
    assert a.stats.total_members == 1 and a.stats.total_users == 1
    b = await port.get_clan_detail(clan_b)
    assert b.stats.total_members == 2 and b.stats.total_users == 1
