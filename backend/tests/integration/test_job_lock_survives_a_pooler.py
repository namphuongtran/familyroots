"""Both scheduled jobs hold a lock that a transaction pooler cannot leak (ADR-065).

Each job takes ``pg_try_advisory_xact_lock`` in one transaction on a dedicated lock
connection, and does its work, committing as it goes, on a separate session. These tests
read the two outcomes that topology exists for, against the real migrated Postgres, for
``send_anniversary_notifications`` and ``purge_expired_documents`` alike:

1. **A second, concurrent run skips.** The first run is held mid-work, inside the
   notification send or the blob delete, so it holds the lock with work still to commit.
   A second run must return without doing any work. Then the first run is released and
   finishes.

2. **A later run takes the lock and does the work.** The first run commits several times
   and finishes. Then a second run, on a **different engine**, must acquire the lock and
   process new work.

   The two engines model what Vercel plus Supavisor look like from the database. Each
   Vercel instance is its own client. The first engine keeps a QueuePool, so its server
   connections outlive the job, the way a pooler's server connections outlive the client
   transaction that used them. A lock left on one of them is therefore still held when the
   second "instance" asks. That is the leak the session-level lock had: it was taken in one
   transaction and unlocked in a later one, which a pooler may run on a different server
   connection. Restoring that lock, with the unlock moved to the work session's
   connection, makes the second run skip and this test fail. That is its negative
   control, recorded in the commit that added this module.

Behind a real direct connection the old lock released when its connection closed, so a
same-engine rerun could not tell the two topologies apart. The second engine is what can.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
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
from app.core.config import settings
from app.services import scheduler
from app.services.document_purge import purge_expired_documents

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# Generous, so a slow CI box never flakes, and finite, so a run that blocks instead of
# skipping fails the test rather than hanging the suite.
_TIMEOUT_S = 10.0


def _platform_today() -> date:
    """The anniversary job's own clock (see test_scheduler_lock.py)."""
    return datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE)).date()


@dataclass
class _Gate:
    """Counts entries into the job's work step, and can hold the first one there."""

    hold_first: bool = False
    calls: int = 0
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)

    async def pass_through(self) -> None:
        self.calls += 1
        self.entered.set()
        if self.hold_first and self.calls == 1:
            await self.release.wait()


@dataclass
class _Job:
    """One scheduled job, as the tests need to drive and observe it."""

    name: str
    install: Callable[[pytest.MonkeyPatch, _Gate], None]
    reset: Callable[[async_sessionmaker[AsyncSession]], Awaitable[None]]
    seed: Callable[[async_sessionmaker[AsyncSession]], Awaitable[uuid.UUID]]
    run: Callable[[], Coroutine[Any, Any, None]]
    done: Callable[[async_sessionmaker[AsyncSession], list[uuid.UUID]], Awaitable[set[uuid.UUID]]]


# ── the anniversary job ───────────────────────────────────────────────────────


def _install_anniversary(monkeypatch: pytest.MonkeyPatch, gate: _Gate) -> None:
    async def send_to_clan(**_: Any) -> tuple[int, int]:
        await gate.pass_through()
        return 1, 0

    monkeypatch.setattr("app.services.notification.send_to_clan", send_to_clan)


async def _reset_anniversary(maker: async_sessionmaker[AsyncSession]) -> None:
    # The job scans every clan's events, so another module's leftovers would count here.
    async with maker() as s:
        await s.execute(sa.text("DELETE FROM notification_log"))
        await s.execute(sa.text("DELETE FROM events"))
        await s.commit()


async def _seed_anniversary(maker: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    """A clan with one recurring solar event due exactly notify_days_before (7) days out.
    Returns the event id."""
    clan_id, event_id = uuid.uuid4(), uuid.uuid4()
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:i, 'C', :sg)"),
            {"i": clan_id, "sg": f"c{clan_id.hex[:10]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events (id, clan_id, event_type, title, event_date, is_recurring, "
                "notify_days_before, created_by) "
                "VALUES (:i, :c, 'death_anniversary', 'Giỗ', :d, true, 7, :cb)"
            ),
            {
                "i": event_id,
                "c": clan_id,
                "d": _platform_today() + timedelta(days=7),
                "cb": uuid.uuid4(),
            },
        )
        await s.commit()
    return event_id


async def _run_anniversary() -> None:
    await scheduler.send_anniversary_notifications(today=_platform_today())


async def _anniversary_done(
    maker: async_sessionmaker[AsyncSession], ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    async with maker() as s:
        rows = await s.execute(
            sa.text("SELECT event_id FROM notification_log WHERE event_id = ANY(:ids)"),
            {"ids": ids},
        )
        return {r[0] for r in rows}


# ── the purge job ─────────────────────────────────────────────────────────────


def _install_purge(monkeypatch: pytest.MonkeyPatch, gate: _Gate) -> None:
    class _Storage:
        async def delete(self, storage_path: str) -> bool:
            await gate.pass_through()
            return True

    monkeypatch.setattr("app.services.document_purge.SupabaseStorageAdapter", _Storage)


async def _reset_purge(maker: async_sessionmaker[AsyncSession]) -> None:
    async with maker() as s:
        await s.execute(sa.text("DELETE FROM documents"))
        await s.commit()


async def _seed_purge(maker: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    """One soft-deleted document well past retention. Returns its id."""
    clan_id, doc_id, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:i, 'C', :sg)"),
            {"i": clan_id, "sg": f"c{clan_id.hex[:10]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO documents (id, clan_id, title, document_type, storage_path, "
                "is_avatar, is_deleted, deleted_at, deleted_by, created_by) "
                "VALUES (:i, :c, 'T', 'photo', :sp, false, true, :da, :a, :a)"
            ),
            {
                "i": doc_id,
                "c": clan_id,
                "sp": f"clans/{clan_id}/documents/{doc_id}.jpg",
                "da": datetime.now(UTC) - timedelta(days=settings.DOCUMENT_RETENTION_DAYS + 10),
                "a": actor,
            },
        )
        await s.commit()
    return doc_id


async def _run_purge() -> None:
    await purge_expired_documents()


async def _purge_done(
    maker: async_sessionmaker[AsyncSession], ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    async with maker() as s:
        rows = await s.execute(
            sa.text("SELECT id FROM documents WHERE id = ANY(:ids)"), {"ids": ids}
        )
        remaining = {r[0] for r in rows}
    return set(ids) - remaining


_JOBS = [
    _Job(
        "anniversary_notifications",
        _install_anniversary,
        _reset_anniversary,
        _seed_anniversary,
        _run_anniversary,
        _anniversary_done,
    ),
    _Job("document_purge", _install_purge, _reset_purge, _seed_purge, _run_purge, _purge_done),
]


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
async def instance_engines(migrated_db_url: str) -> AsyncIterator[tuple[AsyncEngine, AsyncEngine]]:
    """Two engines, two "instances". Both are disposed only at teardown, so the first
    one's server connections stay open across the second run, as a pooler's do."""
    first = create_async_engine(migrated_db_url)
    second = create_async_engine(migrated_db_url)
    yield first, second
    await first.dispose()
    await second.dispose()


def _point_job_at(monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine) -> None:
    monkeypatch.setattr("app.core.database.engine", engine)
    monkeypatch.setattr(
        "app.core.database.AsyncSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )


def _maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# ── the tests ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("job", _JOBS, ids=lambda j: j.name)
async def test_a_second_concurrent_run_skips(
    job: _Job,
    instance_engines: tuple[AsyncEngine, AsyncEngine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, _ = instance_engines
    maker = _maker(engine)
    _point_job_at(monkeypatch, engine)
    gate = _Gate(hold_first=True)
    job.install(monkeypatch, gate)
    await job.reset(maker)
    ids = [await job.seed(maker)]

    first = asyncio.create_task(job.run())
    try:
        await asyncio.wait_for(gate.entered.wait(), _TIMEOUT_S)
        # The first run now holds the lock with its work uncommitted. The second must
        # return on its own, without entering the work step.
        try:
            await asyncio.wait_for(job.run(), _TIMEOUT_S)
        except TimeoutError:
            # The purge job's second run, if it does not skip, blocks on the row the first
            # run has claimed and not yet committed.
            pytest.fail(
                f"{job.name}: the second run did not return. It did not skip, and is "
                "waiting on the first run's uncommitted work"
            )
        assert gate.calls == 1, (
            f"{job.name}: a second run entered the work step while the first held the lock"
        )
        assert await job.done(maker, ids) == set(), "the second run committed work"
    finally:
        gate.release.set()
        await asyncio.wait_for(first, _TIMEOUT_S)

    assert await job.done(maker, ids) == set(ids), "the first run did not finish its work"


@pytest.mark.parametrize("job", _JOBS, ids=lambda j: j.name)
async def test_a_later_run_on_another_instance_takes_the_lock_and_does_the_work(
    job: _Job,
    instance_engines: tuple[AsyncEngine, AsyncEngine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_instance, second_instance = instance_engines
    maker = _maker(second_instance)
    gate = _Gate()
    job.install(monkeypatch, gate)
    await job.reset(maker)

    # Run 1, on the first instance, commits once per item: three commits.
    first_ids = [await job.seed(maker) for _ in range(3)]
    _point_job_at(monkeypatch, first_instance)
    await asyncio.wait_for(job.run(), _TIMEOUT_S)
    assert await job.done(maker, first_ids) == set(first_ids)
    assert gate.calls == 3

    # Run 2, on the second instance, while the first instance's connections live on.
    second_ids = [await job.seed(maker)]
    _point_job_at(monkeypatch, second_instance)
    await asyncio.wait_for(job.run(), _TIMEOUT_S)

    assert await job.done(maker, second_ids) == set(second_ids), (
        f"{job.name}: the second run did no work. The first run's lock outlived it on a "
        "connection the first instance still holds, so every later run would skip, silently"
    )
    assert gate.calls == 4
