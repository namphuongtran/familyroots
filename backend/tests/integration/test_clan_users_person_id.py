"""GET /clans/me/users (and /clans/me/users/pending) must surface each user's
linked person_id.

Regression: ``list_clan_users`` (app/api/v1/clans.py) read ``u.person_id`` off a
raw ``UserClanRole`` ORM row, which has no such column (the link lives on
``user_profiles.person_id``) -- every call with an approved member raised
``AttributeError`` -> 500. The fix LEFT JOINs ``user_profiles`` in
``SqlAlchemyClanRepository.list_users`` so the route can read the real value
(or ``None`` when the user has no profile / no linked person).

Drives the actual route function (as ``test_last_admin_race.py`` drives command
handlers directly) against a real Postgres-backed repository/session -- no HTTP
layer, no auth/JWT stubbing needed since ``list_clan_users`` takes its
dependencies as plain arguments.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.clans import list_clan_users, list_pending_users
from app.application.clan.handlers import ClanQueryHandler
from app.core.permissions import ClanRole
from app.infrastructure.persistence.clan_repository import SqlAlchemyClanRepository

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


async def _profile(s: AsyncSession, uid: uuid.UUID, person_id: uuid.UUID | None = None) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO user_profiles (id, email, display_name, person_id) "
            "VALUES (:id, :e, 'U', :pid)"
        ),
        {"id": uid, "e": f"u-{uid.hex[:8]}@ex.com", "pid": person_id},
    )


async def _role(
    s: AsyncSession, uid: uuid.UUID, cid: uuid.UUID, *, role: str = "admin", approved: bool = True
) -> None:
    now = datetime.now(UTC) if approved else None
    approved_by = uid if approved else None
    await s.execute(
        sa.text(
            "INSERT INTO user_clan_roles "
            "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
            "VALUES (:u, :c, :r, :appr, :ab, :at)"
        ),
        {"u": uid, "c": cid, "r": role, "appr": approved, "ab": approved_by, "at": now},
    )


def _query_handler(session: AsyncSession) -> ClanQueryHandler:
    return ClanQueryHandler(SqlAlchemyClanRepository(session))  # type: ignore[arg-type]


async def test_list_clan_users_returns_linked_person_id(async_session: AsyncSession) -> None:
    clan_id, user_id = uuid.uuid4(), uuid.uuid4()
    await _clan(async_session, clan_id)
    person_id = await _person(async_session, clan_id, user_id)
    await _profile(async_session, user_id, person_id)
    await _role(async_session, user_id, clan_id)
    await async_session.commit()

    page = await list_clan_users(
        current_user={"sub": str(user_id)},
        clan_id=clan_id,
        query_handler=_query_handler(async_session),
        role=ClanRole.VIEWER,
        cursor=None,
        limit=20,
    )

    assert len(page["data"]) == 1
    row = page["data"][0]
    assert row["user_id"] == str(user_id)
    assert row["person_id"] == str(person_id)


async def test_list_clan_users_person_id_null_without_linked_person(
    async_session: AsyncSession,
) -> None:
    clan_id, user_id = uuid.uuid4(), uuid.uuid4()
    await _clan(async_session, clan_id)
    await _profile(async_session, user_id, None)  # no linked person
    await _role(async_session, user_id, clan_id)
    await async_session.commit()

    page = await list_clan_users(
        current_user={"sub": str(user_id)},
        clan_id=clan_id,
        query_handler=_query_handler(async_session),
        role=ClanRole.VIEWER,
        cursor=None,
        limit=20,
    )

    assert len(page["data"]) == 1
    assert page["data"][0]["person_id"] is None


async def test_list_pending_users_includes_person_id(async_session: AsyncSession) -> None:
    """/pending now includes person_id (ADR-024): present, with the linked
    person's id when the pending user has one (or None otherwise)."""
    clan_id, user_id = uuid.uuid4(), uuid.uuid4()
    await _clan(async_session, clan_id)
    person_id = await _person(async_session, clan_id, user_id)
    await _profile(async_session, user_id, person_id)
    await _role(async_session, user_id, clan_id, role="viewer", approved=False)
    await async_session.commit()

    page = await list_pending_users(
        current_user={"sub": str(user_id)},
        clan_id=clan_id,
        query_handler=_query_handler(async_session),
        role=ClanRole.ADMIN,
        cursor=None,
        limit=20,
    )

    assert len(page["data"]) == 1
    assert page["data"][0]["person_id"] == str(person_id)
