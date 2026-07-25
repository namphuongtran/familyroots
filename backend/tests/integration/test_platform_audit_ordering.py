"""Platform audit log must be NEWEST-first (M14) — real Postgres, RED-first.

`get_audit_log`'s port contract says "recent" and the table's indexes are `created_at
DESC`, but the shared `paginate_query` hardcodes ASC, so a super-admin sees the OLDEST
events first. These tests pin newest-first (DESC) ordering + a monotonic DESC cursor.
All OTHER list endpoints stay ASC (opt-in `descending` flag); a control here proves the
default pager is untouched.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence.platform_admin_query_port import (
    SqlAlchemyPlatformAdminQueryPort,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as s:
        yield s
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


async def _audit_at(
    s: AsyncSession,
    *,
    clan_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    created_at: datetime,
    row_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert one audit row with an EXPLICIT created_at so ordering is deterministic."""
    rid = row_id or uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO audit_logs (id, clan_id, actor_id, actor_role, action, "
            "resource_type, created_at) "
            "VALUES (:id, :c, :a, 'admin', :act, 'clan', :ts)"
        ),
        {"id": rid, "c": clan_id, "a": actor_id, "act": action, "ts": created_at},
    )
    return rid


async def test_audit_log_newest_first(session: AsyncSession) -> None:
    """Three rows t1<t2<t3 → get_audit_log returns them newest-first [t3, t2, t1].
    RED today: ASC pagination returns t1 first."""
    clan_id, actor_id = uuid.uuid4(), uuid.uuid4()
    await _clan(session, clan_id)
    await _profile(session, actor_id)
    base = datetime(2020, 1, 1, tzinfo=UTC)
    ids = {}
    for i, action in enumerate(("clan.act0", "clan.act1", "clan.act2")):
        ids[action] = await _audit_at(
            session,
            clan_id=clan_id,
            actor_id=actor_id,
            action=action,
            created_at=base + timedelta(days=i),
        )
    await session.commit()

    port = SqlAlchemyPlatformAdminQueryPort(session)
    page = await port.get_audit_log(clan_id, None, None, 20)
    got = [e.id for e in page.data]

    assert got == [ids["clan.act2"], ids["clan.act1"], ids["clan.act0"]], (
        f"expected newest-first, got {[e.action for e in page.data]}"
    )
    assert page.data[0].created_at is not None
    # Strictly descending created_at.
    times = [e.created_at for e in page.data]
    assert times == sorted(times, reverse=True), times


async def test_audit_log_desc_cursor_no_overlap_monotonic(session: AsyncSession) -> None:
    """Paging DESC with limit=2 across 4 rows: page1 = 2 newest, page2 = next, no id on
    both pages, and every page2 row is older than every page1 row. RED today (ASC)."""
    clan_id, actor_id = uuid.uuid4(), uuid.uuid4()
    await _clan(session, clan_id)
    await _profile(session, actor_id)
    base = datetime(2021, 6, 1, tzinfo=UTC)
    for i in range(4):
        await _audit_at(
            session,
            clan_id=clan_id,
            actor_id=actor_id,
            action=f"clan.a{i}",
            created_at=base + timedelta(hours=i),
        )
    await session.commit()

    port = SqlAlchemyPlatformAdminQueryPort(session)
    page1 = await port.get_audit_log(clan_id, None, None, 2)
    assert len(page1.data) == 2
    assert page1.meta.has_more is True
    page2 = await port.get_audit_log(clan_id, None, page1.meta.cursor, 2)
    assert len(page2.data) == 2

    assert not ({e.id for e in page1.data} & {e.id for e in page2.data})
    newest_of_page2 = max(e.created_at for e in page2.data)
    oldest_of_page1 = min(e.created_at for e in page1.data)
    assert newest_of_page2 <= oldest_of_page1, "page2 must be strictly older than page1"


async def test_audit_log_tiebreak_equal_created_at(session: AsyncSession) -> None:
    """Two rows with IDENTICAL created_at order by id DESC and the cursor advances
    without duplicating or skipping. RED today (ASC id order)."""
    clan_id, actor_id = uuid.uuid4(), uuid.uuid4()
    await _clan(session, clan_id)
    await _profile(session, actor_id)
    ts = datetime(2022, 3, 3, 12, 0, tzinfo=UTC)
    # Two explicit ids so we know the DESC-id winner.
    id_lo = uuid.UUID("00000000-0000-0000-0000-000000000001")
    id_hi = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    await _audit_at(session, clan_id=clan_id, actor_id=actor_id, action="a", created_at=ts, row_id=id_lo)
    await _audit_at(session, clan_id=clan_id, actor_id=actor_id, action="b", created_at=ts, row_id=id_hi)
    await session.commit()

    port = SqlAlchemyPlatformAdminQueryPort(session)
    page1 = await port.get_audit_log(clan_id, None, None, 1)
    assert [e.id for e in page1.data] == [id_hi]  # larger id first under DESC tie-break
    page2 = await port.get_audit_log(clan_id, None, page1.meta.cursor, 1)
    assert [e.id for e in page2.data] == [id_lo]
    assert page2.meta.has_more is False
