"""The two Vercel Cron routes run the REAL jobs against the real database (ADR-065).

``tests/unit/test_cron_endpoints.py`` pins the authentication matrix with the jobs replaced
by spies. This module keeps the jobs real and reads their effect on the migrated Postgres:

- ``GET /internal/cron/anniversary-notifications`` with the secret writes a
  ``notification_log`` row for a due event. With a wrong secret, it writes none.
- ``GET /internal/cron/document-purge`` with the secret deletes an expired soft-deleted
  document. With a wrong secret, the document survives.

Only the edges are faked: the FCM fan-out (``send_to_clan``) and the storage adapter. The
app is driven in this test's event loop through ``ASGITransport``, because the job's engine
is created here and an async connection cannot cross into the thread that ``TestClient``
runs the app on. ``ASGITransport`` sends no lifespan events, so APScheduler never starts.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.database  # noqa: F401 — imported early so _reset_settings cannot rebind it
from app.api.cron import ANNIVERSARY_NOTIFICATIONS_PATH, DOCUMENT_PURGE_PATH
from app.core.config import MIN_METRICS_TOKEN_LENGTH, settings
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_SECRET = (("not-a-real-secret-" + "0123456789abcdef") * 2)[:MIN_METRICS_TOKEN_LENGTH]
_RIGHT = {"Authorization": f"Bearer {_SECRET}"}
_WRONG = {"Authorization": "Bearer not-the-secret-0123456789abcdef"}


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.fixture()
def maker(engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> async_sessionmaker[AsyncSession]:
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", sessions)
    monkeypatch.setattr(settings, "CRON_SECRET", _SECRET)
    return sessions


@pytest.fixture()
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def _seed_due_event(maker: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    today = datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE)).date()
    clan_id, event_id = uuid.uuid4(), uuid.uuid4()
    async with maker() as s:
        # The job scans every clan; start from a clean slate.
        await s.execute(sa.text("DELETE FROM notification_log"))
        await s.execute(sa.text("DELETE FROM events"))
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
            {"i": event_id, "c": clan_id, "d": today + timedelta(days=7), "cb": uuid.uuid4()},
        )
        await s.commit()
    return event_id


async def _logged(maker: async_sessionmaker[AsyncSession], event_id: uuid.UUID) -> int:
    async with maker() as s:
        n = await s.scalar(
            sa.text("SELECT count(*) FROM notification_log WHERE event_id = :e"), {"e": event_id}
        )
    return int(n or 0)


async def test_the_anniversary_route_runs_the_real_job_only_for_the_secret(
    maker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    send = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", send)
    event_id = await _seed_due_event(maker)

    refused = await client.get(ANNIVERSARY_NOTIFICATIONS_PATH, headers=_WRONG)
    assert refused.status_code == 404
    assert await _logged(maker, event_id) == 0
    assert send.await_count == 0

    ran = await client.get(ANNIVERSARY_NOTIFICATIONS_PATH, headers=_RIGHT)
    assert ran.status_code == 204
    assert await _logged(maker, event_id) == 1
    assert send.await_count == 1

    # A duplicate delivery, which Vercel documents, is a no-op: the job's own dedup.
    again = await client.get(ANNIVERSARY_NOTIFICATIONS_PATH, headers=_RIGHT)
    assert again.status_code == 204
    assert await _logged(maker, event_id) == 1
    assert send.await_count == 1


async def test_the_purge_route_runs_the_real_job_only_for_the_secret(
    maker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted: list[str] = []

    class _Storage:
        async def delete(self, storage_path: str) -> bool:
            deleted.append(storage_path)
            return True

    monkeypatch.setattr("app.services.document_purge.SupabaseStorageAdapter", _Storage)

    clan_id, doc_id, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    path = f"clans/{clan_id}/documents/{doc_id}.jpg"
    async with maker() as s:
        await s.execute(sa.text("DELETE FROM documents"))
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
                "sp": path,
                "da": datetime.now(UTC) - timedelta(days=settings.DOCUMENT_RETENTION_DAYS + 10),
                "a": actor,
            },
        )
        await s.commit()

    async def remaining() -> int:
        async with maker() as s:
            n = await s.scalar(
                sa.text("SELECT count(*) FROM documents WHERE id = :i"), {"i": doc_id}
            )
        return int(n or 0)

    refused = await client.get(DOCUMENT_PURGE_PATH, headers=_WRONG)
    assert refused.status_code == 404
    assert await remaining() == 1
    assert deleted == []

    ran = await client.get(DOCUMENT_PURGE_PATH, headers=_RIGHT)
    assert ran.status_code == 204
    assert await remaining() == 0
    assert deleted == [path]
