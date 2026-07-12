"""Pre-merge review Finding 3: GET /events/upcoming must compute ``today`` in the
platform timezone (``settings.SCHEDULER_TIMEZONE``), not the server-local
``date.today()`` — a container running in a different system timezone than the
platform's would otherwise gate "is it N days away" against the wrong day.

The fix computes ``today`` in the ROUTE layer (which already legally imports
``app.core.config`` — see ``app/api/v1/documents.py`` for precedent) and threads it
into the handler, keeping ``app.application`` free of a new ``app.core`` import (the
import-linter ratchet for ``app.application`` -> ``app.core`` must not grow).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.api.v1 import events
from app.core.config import settings
from app.core.permissions import ClanRole


@pytest.mark.asyncio
async def test_get_upcoming_events_passes_platform_tz_today_to_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exotic zone far from any plausible container-local zone (UTC+14) — if the
    route ever regresses to server-local date.today(), this only coincidentally
    matches around the zone's midnight, so it reliably catches the bug."""
    exotic_tz = "Pacific/Kiritimati"
    # `events.settings` is the same object (from app.core.config import settings) —
    # patching the shared singleton's attribute, not a module-level rebind.
    monkeypatch.setattr(settings, "SCHEDULER_TIMEZONE", exotic_tz)

    captured: dict[str, Any] = {}

    class _CapturingQueryHandler:
        async def get_upcoming(
            self, *, clan_id: uuid.UUID, days: int = 30, today: date | None = None
        ) -> list[dict[str, Any]]:
            captured["clan_id"] = clan_id
            captured["days"] = days
            captured["today"] = today
            return []

    clan_id = uuid.uuid4()
    before = datetime.now(ZoneInfo(exotic_tz)).date()
    await events.get_upcoming_events(
        days=30,
        current_user={"sub": str(uuid.uuid4())},
        clan_id=clan_id,
        query_handler=_CapturingQueryHandler(),  # type: ignore[arg-type]
        role=ClanRole.VIEWER,
        include=None,
    )
    after = datetime.now(ZoneInfo(exotic_tz)).date()

    assert captured["clan_id"] == clan_id
    assert captured["days"] == 30
    # Bound any clock drift across the call to the same (monkeypatched-zone) day.
    assert captured["today"] in (before, after)
