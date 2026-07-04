"""Tests for notification scheduler and deduplication logic."""

import asyncio
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def clan_id():
    return uuid.uuid4()


@pytest.mark.asyncio
async def test_scheduler_starts_and_stops():
    """Scheduler starts and stops without error."""
    from app.services.scheduler import scheduler, start_scheduler, stop_scheduler

    start_scheduler()
    assert scheduler.running is True
    stop_scheduler()
    await asyncio.sleep(0)  # let event loop process the shutdown callback
    assert scheduler.running is False


class _FakeConnCtx:
    """Minimal async context manager standing in for ``engine.connect()``.

    Real ``MagicMock``/``AsyncMock`` async-dunder support is version-fiddly;
    a tiny hand-written class keeps this unit test's await semantics obvious.
    """

    def __init__(self, conn: AsyncMock) -> None:
        self._conn = conn

    async def __aenter__(self) -> AsyncMock:
        return self._conn

    async def __aexit__(self, *exc: object) -> bool:
        return False


@pytest.mark.asyncio
async def test_anniversary_dedup_skips_already_sent():
    """Already-sent notifications are not re-sent (dedup via notification_log)."""
    from app.services.scheduler import send_anniversary_notifications

    mock_db = AsyncMock()
    today = date.today()
    notify_days = 3

    # Build stable mock values (uuid.uuid4() must not be called per-access)
    ev_id = uuid.uuid4()
    ev_clan = uuid.uuid4()
    ev_person = uuid.uuid4()

    # Return an event row
    event_row = MagicMock()
    event_row.__getitem__ = lambda self, key: {
        "event_id": ev_id,
        "event_type": "death_anniversary",
        "title": "Test Anniversary",
        "clan_id": ev_clan,
        "person_id": ev_person,
        "person_name": "Ancestor",
        "notify_days_before": notify_days,
        "next_occurrence": today + timedelta(days=notify_days),
    }[key]

    events_result = MagicMock()
    events_result.mappings.return_value.all.return_value = [event_row]

    # notification_log check: already exists
    dedup_result = MagicMock()
    dedup_result.first.return_value = 1  # exists -> `if dedup.first(): continue`

    execute_calls = []

    async def mock_execute(query, params=None):
        execute_calls.append(str(query))
        if len(execute_calls) == 1:
            return events_result
        return dedup_result

    mock_db.execute = AsyncMock(side_effect=mock_execute)
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.close = AsyncMock()

    # Lock topology (C2): the job acquires the advisory lock on a dedicated
    # connection (``engine.connect()``), then binds a session to it.
    lock_result = MagicMock()
    lock_result.scalar.return_value = True  # lock acquired
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=lock_result)

    mock_engine = MagicMock()
    mock_engine.connect = MagicMock(return_value=_FakeConnCtx(mock_conn))

    with (
        patch("app.core.database.engine", mock_engine),
        patch("app.services.scheduler.AsyncSession", return_value=mock_db),
        patch("app.services.notification.send_to_clan") as mock_send,
    ):
        await send_anniversary_notifications()
        # send_to_clan should NOT be called because dedup found existing entry
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_firebase_init_handles_missing_credentials():
    """init_firebase does not raise when credentials file is missing."""
    with patch("app.services.notification.settings") as mock_settings:
        mock_settings.FIREBASE_CREDENTIALS_PATH = "/nonexistent/path.json"
        from app.services.notification import init_firebase

        # Should not raise, just log a warning
        init_firebase()
