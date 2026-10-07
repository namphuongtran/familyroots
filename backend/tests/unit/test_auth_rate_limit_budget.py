"""Where the `/api/v1/auth` + `/api/v1/invitations` bucket refuses a request (ADR-021, #226).

ADR-021 Decision 3 put both prefixes behind one limiter at 20 requests per 60 seconds per IP.
Its amendment of 2026-10-07 (#226) reads the count from ``RATE_LIMIT_AUTH_MAX_REQUESTS`` so
that the authenticated e2e harness's backend can raise it, while every deployment that sets
nothing keeps 20. The window stays 60 seconds.

Every case here builds the app with ``create_app()``, sends real requests through its real
middleware stack, and reads the status codes. None reads the middleware's constructor
arguments: those are the setting, and a test that asserts a setting cannot fail for the
reason anyone cares about (``.claude/rules/testing.md``, "A test pins an outcome, not a
setting"). The reading that matters is which request in the window answers 429.

The probe is ``GET /api/v1/auth/me`` with no token, the request the harness spends most,
answered 401 by ``get_current_user`` before any session is used. ``get_db`` is replaced
anyway, so no case can reach a database whatever the route does.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from pydantic import ValidationError

import app.main as main_module
from app.core.config import Settings
from app.core.database import get_db
from app.main import create_app

pytestmark = pytest.mark.unit

_SETTING = "RATE_LIMIT_AUTH_MAX_REQUESTS"
_PROBE = "/api/v1/auth/me"


async def _no_db() -> AsyncIterator[None]:
    yield None


def _app(monkeypatch: pytest.MonkeyPatch, value: str | None) -> FastAPI:
    """The real app, built on settings read from the environment with *value* in it.

    ``_env_file=None`` so a developer's ``backend/.env`` cannot decide the reading. ``value``
    of ``None`` removes the variable, which is what every production deployment does today.
    """
    if value is None:
        monkeypatch.delenv(_SETTING, raising=False)
    else:
        monkeypatch.setenv(_SETTING, value)
    monkeypatch.setattr(main_module, "settings", Settings(_env_file=None))
    application = create_app()
    application.dependency_overrides[get_db] = _no_db
    return application


async def _statuses(application: FastAPI, count: int) -> list[int]:
    """Send *count* probes from one client address, inside one window, and read each status."""
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return [(await client.get(_PROBE)).status_code for _ in range(count)]


async def test_with_nothing_set_the_21st_request_in_the_window_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production's budget, unchanged by #226: twenty admitted, the twenty-first refused."""
    statuses = await _statuses(_app(monkeypatch, None), 21)

    assert 429 not in statuses[:20], statuses
    assert statuses[20] == 429, statuses


async def test_raised_the_same_21st_request_is_admitted_and_the_new_boundary_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raised to 25, the request the default refuses is admitted, and the 26th is refused.

    The second half is what keeps "raised" from passing as "off": a limiter that stopped
    counting would admit the 26th too.
    """
    statuses = await _statuses(_app(monkeypatch, "25"), 26)

    assert statuses[20] != 429, statuses
    assert 429 not in statuses[:25], statuses
    assert statuses[25] == 429, statuses


@pytest.mark.parametrize("value", ["0", "-5"])
def test_a_budget_that_admits_nothing_refuses_to_boot(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Zero or less would answer 429 to every sign-in, so settings refuse it by name."""
    monkeypatch.setenv(_SETTING, value)

    with pytest.raises(ValidationError, match=_SETTING):
        Settings(_env_file=None)
