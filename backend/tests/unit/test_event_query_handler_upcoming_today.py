"""Pre-merge review Finding 3: EventQueryHandler.get_upcoming gains an optional
``today`` parameter — the route (app/api/v1/events.py) passes a platform-TZ-derived
date; other/future callers keep the old server-local date.today() fallback so this
change is backward compatible."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import pytest

from app.application.event.handlers import EventQueryHandler


class _RecordingRepo:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get_upcoming(
        self, clan_id: uuid.UUID, *, today: date, end_date: date, limit: int = 50
    ) -> list[dict[str, Any]]:
        self.calls.append({"clan_id": clan_id, "today": today, "end_date": end_date})
        return []


@pytest.mark.asyncio
async def test_get_upcoming_uses_explicit_today_when_given() -> None:
    repo = _RecordingRepo()
    handler = EventQueryHandler(repo)  # type: ignore[arg-type]
    clan_id = uuid.uuid4()
    explicit_today = date(2030, 6, 15)

    await handler.get_upcoming(clan_id=clan_id, days=10, today=explicit_today)

    assert repo.calls[0]["today"] == explicit_today
    assert repo.calls[0]["end_date"] == explicit_today + timedelta(days=10)


@pytest.mark.asyncio
async def test_get_upcoming_falls_back_to_server_local_today_when_omitted() -> None:
    repo = _RecordingRepo()
    handler = EventQueryHandler(repo)  # type: ignore[arg-type]
    clan_id = uuid.uuid4()

    before = date.today()
    await handler.get_upcoming(clan_id=clan_id, days=10)
    after = date.today()

    assert repo.calls[0]["today"] in (before, after)
