"""Tests for notification scheduler and deduplication logic."""

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
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
    ev_member = uuid.uuid4()

    # Return an event row
    event_row = MagicMock()
    event_row.__getitem__ = lambda self, key: {
        "event_id": ev_id,
        "event_type": "death_anniversary",
        "title": "Test Anniversary",
        "clan_id": ev_clan,
        "member_id": ev_member,
        "member_name": "Ancestor",
        "notify_days_before": notify_days,
        "next_occurrence": today + timedelta(days=notify_days),
    }[key]

    events_result = MagicMock()
    events_result.mappings.return_value.all.return_value = [event_row]

    # notification_log check: already exists
    dedup_result = MagicMock()
    dedup_result.scalar_one_or_none.return_value = 1  # exists

    execute_calls = []

    async def mock_execute(query, params=None):
        execute_calls.append(str(query))
        if len(execute_calls) == 1:
            return events_result
        return dedup_result

    mock_db.execute = AsyncMock(side_effect=mock_execute)

    with patch(
        "app.core.database.AsyncSessionLocal",
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_db),
            __aexit__=AsyncMock(return_value=False),
        ),
    ), patch("app.services.notification.send_to_clan") as mock_send:
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
