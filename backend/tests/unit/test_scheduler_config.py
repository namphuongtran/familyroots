"""M4 — the scheduler is pinned to the platform timezone, not the container's."""

import pytest

from app.core.config import settings
from app.services.scheduler import _TZ, scheduler

pytestmark = [pytest.mark.unit]


def test_scheduler_uses_configured_timezone() -> None:
    # cron "hour=7" must mean 07:00 in the platform zone regardless of the host TZ.
    assert str(scheduler.timezone) == settings.SCHEDULER_TIMEZONE
    assert str(_TZ) == settings.SCHEDULER_TIMEZONE
