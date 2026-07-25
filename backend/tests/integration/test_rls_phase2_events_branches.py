"""RLS layer-2 Phase 2 (SP-3, ADR-008): events + branches are clan-isolated at the DB.

Migration 027 enables the same clan-isolation policy as documents on two more clan-owned
tables. These prove enforcement through the runtime seam (RlsSession + the app.clan_id
ContextVar): a naked read is scoped to the clan, a cross-clan write is rejected by
WITH CHECK, and no clan → zero rows (fail closed). The scheduler reads events via a
privileged system session (proven bypassing in test_rls_activation), so it is unaffected.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import RlsSession
from app.core.rls import set_request_clan_id

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.fixture(autouse=True)
def _reset_clan_context() -> Generator[None]:
    set_request_clan_id(None)
    yield
    set_request_clan_id(None)


async def _seed(conn: AsyncConnection, clan_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    await conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:10]}"},
    )
    event_id, branch_id, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO events (id, clan_id, event_type, title, event_date, created_by) "
            "VALUES (:id, :c, 'birthday', 't', '2000-01-01', :a)"
        ),
        {"id": event_id, "c": clan_id, "a": actor},
    )
    await conn.execute(
        sa.text("INSERT INTO branches (id, clan_id, name) VALUES (:id, :c, 'Chi')"),
        {"id": branch_id, "c": clan_id},
    )
    return event_id, branch_id


async def _seed_two(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID, dict[str, uuid.UUID]]:
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:  # privileged seeding
        ea, ba = await _seed(conn, clan_a)
        eb, bb = await _seed(conn, clan_b)
    return clan_a, clan_b, {"ea": ea, "ba": ba, "eb": eb, "bb": bb}


@pytest.mark.parametrize("table", ["events", "branches"])
async def test_rls_scopes_reads_to_the_active_clan(engine: AsyncEngine, table: str) -> None:
    clan_a, clan_b, ids = await _seed_two(engine)
    rls = async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)
    own = {"events": ids["ea"], "branches": ids["ba"]}[table]
    other = {"events": ids["eb"], "branches": ids["bb"]}[table]

    set_request_clan_id(clan_a)
    async with rls() as s:
        seen = set((await s.execute(sa.text(f"SELECT id FROM {table}"))).scalars().all())
    assert own in seen and other not in seen, (table, seen)


async def test_rls_default_deny_when_no_clan(engine: AsyncEngine) -> None:
    await _seed_two(engine)
    rls = async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)
    set_request_clan_id(None)
    async with rls() as s:
        assert await s.scalar(sa.text("SELECT count(*) FROM events")) == 0
        assert await s.scalar(sa.text("SELECT count(*) FROM branches")) == 0


async def test_with_check_rejects_cross_clan_write(engine: AsyncEngine) -> None:
    """Under GUC = clan A, writing a branch owned by clan B is rejected by WITH CHECK —
    RLS blocks a mislabeled cross-clan INSERT, not just reads."""
    clan_a, clan_b, _ids = await _seed_two(engine)
    rls = async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)
    set_request_clan_id(clan_a)
    async with rls() as s:
        with pytest.raises(sa.exc.DBAPIError) as ei:
            await s.execute(
                sa.text("INSERT INTO branches (id, clan_id, name) VALUES (:id, :c, 'X')"),
                {"id": uuid.uuid4(), "c": clan_b},  # clan B while GUC = clan A
            )
            await s.flush()
        assert "row-level security" in str(ei.value).lower()
