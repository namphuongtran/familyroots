"""The anniversary job still crosses clans after migration 034 — S-014, ADR-043 § 2, item 8.

**This is the path a naive policy breaks silently, and no request test touches it.** The job
is one process serving every clan on the platform: one advisory lock, one query over all of
`events`, one `notification_log` insert per due event
(`docs/architecture/notifications-scheduler.md`, "Multi-replica safety" and
"`notification_log` lifecycle"). If `notification_log_clan_isolation` ever applied to it, the
dedup `SELECT` would return nothing and the `INSERT` would be rejected — and the failure would
not look like a failure. Every clan but one would simply stop receiving giỗ reminders.

It does not apply, for a reason that has to stay true rather than be assumed: the job binds
its `AsyncSession` to a bare `engine.connect()` (`app/services/scheduler.py:90, 102`), which is
**not** an `RlsSession`, so the `after_begin` seam never fires, no `SET LOCAL ROLE` is issued,
and the connection keeps the `DATABASE_URL` login role, which bypasses RLS.

The test therefore asserts three things in one run, and the third is what makes the first two
mean something:

1. two clans' due events both produce a `notification_log` row in a **single** job run;
2. `send_to_clan` was called once per clan, so the fan-out itself crossed the boundary rather
   than one row being written for two events of the same clan;
3. the policy is **live** during that run — checked by reading the same two rows back under
   the request role, where clan A sees exactly its own and not clan B's. Without part 3 this
   whole file would pass just as happily against a database where migration 034 never ran,
   which is precisely the vacuous pass S-012 warned about.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.database  # noqa: F401 — imported early so _reset_settings cannot rebind it
import app.services.scheduler as scheduler
from app.core.config import settings
from app.core.database import RlsSession
from app.core.rls import set_request_clan_id

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_NOTIFY_DAYS = 7


def _platform_today() -> date:
    """The job computes "today" in the platform zone, so the seed must use the same clock.
    Seeding with `date.today()` on a UTC runner in the evening puts the event one platform-day
    short of due and the job (correctly) sends nothing — a time-of-day flake, not a bug."""
    return datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE)).date()


@pytest.fixture()
async def engine(migrated_db_url: str) -> Any:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.fixture(autouse=True)
def _reset_clan_context() -> Any:
    set_request_clan_id(None)
    yield
    set_request_clan_id(None)


async def _seed_due_event(maker: async_sessionmaker[AsyncSession], today: date) -> uuid.UUID:
    """One clan with one recurring solar event due exactly `notify_days_before` days out.
    Returns the clan id. Seeded privileged, which bypasses the policy under test."""
    clan_id, person_id, event_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:i, 'C', :sg)"),
            {"i": clan_id, "sg": f"c{clan_id.hex[:10]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, created_by, is_deleted) "
                "VALUES (:i, 'Tổ tiên', :cb, false)"
            ),
            {"i": person_id, "cb": uuid.uuid4()},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events (id, clan_id, event_type, title, event_date, is_recurring, "
                "is_lunar_calendar, notify_days_before, person_id, created_by) "
                "VALUES (:i, :c, 'death_anniversary', 'Giỗ', :d, true, false, :n, :p, :cb)"
            ),
            {
                "i": event_id,
                "c": clan_id,
                "d": today + timedelta(days=_NOTIFY_DAYS),
                "n": _NOTIFY_DAYS,
                "p": person_id,
                "cb": uuid.uuid4(),
            },
        )
        await s.commit()
    return clan_id


async def test_one_run_writes_a_notification_row_for_each_of_two_clans(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)

    today = _platform_today()
    # Start from a clean slate: the migrated DB is session-scoped and the job scans EVERY
    # clan's events, so another module's leftover due event would land in this run's counts.
    async with maker() as s:
        await s.execute(sa.text("DELETE FROM notification_log"))
        await s.execute(sa.text("DELETE FROM events"))
        await s.commit()

    clan_a = await _seed_due_event(maker, today)
    clan_b = await _seed_due_event(maker, today)

    await scheduler.send_anniversary_notifications()

    # 1 — one row per clan, from ONE run.
    async with maker() as s:
        rows = (
            (
                await s.execute(
                    sa.text("SELECT id, clan_id FROM notification_log WHERE clan_id = ANY(:c)"),
                    {"c": [clan_a, clan_b]},
                )
            )
            .mappings()
            .all()
        )
    by_clan = {r["clan_id"]: r["id"] for r in rows}
    assert set(by_clan) == {clan_a, clan_b}, (
        f"the scheduler stopped crossing clans: wrote for {set(by_clan)}, expected both "
        f"{clan_a} and {clan_b}. A clan policy reaching this job is the likely cause — it "
        f"binds its session to a bare engine.connect(), which must stay seam-free"
    )
    assert len(rows) == 2

    # 2 — the fan-out itself crossed, once per clan.
    assert spy.await_count == 2
    assert {c.kwargs["clan_id"] for c in spy.await_args_list} == {clan_a, clan_b}

    # 3 — and the policy really was live while all of that happened. Without this the test
    # would pass identically against a tree where migration 034 was never applied.
    rls = async_sessionmaker(
        engine, sync_session_class=RlsSession, expire_on_commit=False, class_=AsyncSession
    )
    set_request_clan_id(clan_a)
    async with rls() as s:
        assert await s.scalar(sa.text("SELECT current_user")) == "familyroots_app"
        visible = set(
            (
                await s.execute(
                    sa.text("SELECT id FROM notification_log WHERE clan_id = ANY(:c)"),
                    {"c": [clan_a, clan_b]},
                )
            ).scalars()
        )
    assert visible == {by_clan[clan_a]}, (
        f"notification_log_clan_isolation is not enforcing: under clan A the request role "
        f"saw {visible}, expected only {by_clan[clan_a]}"
    )
