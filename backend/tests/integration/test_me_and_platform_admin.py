"""Coverage for the previously-untested me + platform_admin contexts (2026-06-28 review).

- me.list_clans returns only APPROVED memberships; select_clan 403s a non-member.
- platform_admin suspend/reactivate flips clan.is_active and writes an audit row.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.application.me.handlers import MeQueryHandler
from app.application.platform_admin.handlers import PlatformAdminCommandHandler
from app.core.exceptions import ForbiddenError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.clan_repository import SqlAlchemyClanRepository
from app.infrastructure.persistence.me_query_port import SqlAlchemyMeQueryPort
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(migrated_db_url)
    yield engine
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


async def _role(s: AsyncSession, uid: uuid.UUID, cid: uuid.UUID, *, approved: bool) -> None:
    now = datetime.now(UTC)
    await s.execute(
        sa.text(
            "INSERT INTO user_clan_roles "
            "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
            "VALUES (:u, :c, 'admin', :ap, :ab, :at)"
        ),
        {
            "u": uid,
            "c": cid,
            "ap": approved,
            "ab": uid if approved else None,
            "at": now if approved else None,
        },
    )


async def test_me_lists_only_approved_and_blocks_non_member(async_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    user_id = uuid.uuid4()
    approved_clan, pending_clan, other_clan = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        for cid in (approved_clan, pending_clan, other_clan):
            await _clan(s, cid)
        await _profile(s, user_id)
        await _role(s, user_id, approved_clan, approved=True)
        await _role(s, user_id, pending_clan, approved=False)  # pending → excluded
        await s.commit()

        handler = MeQueryHandler(SqlAlchemyMeQueryPort(s))

        clans = await handler.list_clans(user_id=str(user_id))
        ids = {c["clan_id"] for c in clans["clans"]}
        assert ids == {str(approved_clan)}  # only the approved membership
        assert clans["count"] == 1

        # select an approved clan → ok
        selected = await handler.select_clan(user_id=str(user_id), clan_id=approved_clan)
        assert selected["clan_id"] == str(approved_clan)

        # select a clan the user is not an approved member of → 403
        with pytest.raises(ForbiddenError):
            await handler.select_clan(user_id=str(user_id), clan_id=other_clan)
        with pytest.raises(ForbiddenError):
            await handler.select_clan(user_id=str(user_id), clan_id=pending_clan)


async def test_platform_admin_suspend_and_reactivate(async_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, admin_id = uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        await _clan(s, clan_id)
        await s.commit()

        async def _is_active() -> bool:
            return bool(
                await s.scalar(sa.text("SELECT is_active FROM clans WHERE id = :c"), {"c": clan_id})
            )

        async def _audit_count() -> int:
            sql = "SELECT count(*) FROM audit_logs WHERE clan_id = :c AND resource_type = 'clan'"
            return (await s.execute(sa.text(sql), {"c": clan_id})).scalar() or 0

        actor = ActorInfo.from_jwt({"sub": str(admin_id)}, "admin")
        # SqlAlchemyClanRepository satisfies what PlatformAdminCommandHandler uses
        # (load + mutate clan); its list_users return type differs from the port
        # (a known Minor mismatch) — not exercised here.
        handler = PlatformAdminCommandHandler(
            SqlAlchemyClanRepository(s),  # type: ignore[arg-type]
            SqlAlchemyUnitOfWork(s, create_event_dispatcher(s)),
        )

        assert await _is_active() is True
        await handler.suspend_clan(clan_id=clan_id, actor=actor)
        assert await _is_active() is False  # suspension flips the flag
        await handler.reactivate_clan(clan_id=clan_id, actor=actor)
        assert await _is_active() is True
        assert await _audit_count() >= 2  # suspend + reactivate both audited
