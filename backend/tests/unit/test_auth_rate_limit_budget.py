"""Where the auth rate limit's bucket refuses a request (ADR-021, #226, #280).

ADR-021 Decision 3 put the auth and invitation-accept routes behind one limiter at 20 requests
per 60 seconds per IP. Its amendment of 2026-10-07 (#226) reads the count from
``RATE_LIMIT_AUTH_MAX_REQUESTS`` so that the authenticated e2e harness's backend can raise it,
while every deployment that sets nothing keeps 20. The window stays 60 seconds. Its amendment
of 2026-10-11 (#280) narrowed what the bucket counts from two path prefixes to the seven routes
where an account or a token can be guessed. ``GET /auth/me`` left it, because the web's server
guard sends that request with the web's address, not the user's.

Every case here builds the app with ``create_app()``, sends real requests through its real
middleware stack, and reads the status codes. None reads the middleware's constructor
arguments: those are the setting, and a test that asserts a setting cannot fail for the
reason anyone cares about (``.claude/rules/testing.md``, "A test pins an outcome, not a
setting"). The reading that matters is which request in the window answers 429.

The probe is ``POST /api/v1/auth/login`` with body ``{}``, a counted route that answers 422 at
request validation, before the handler runs. Every other request here is refused before it
would touch a session or the identity provider: a 401 for a missing bearer token, a 404 or 405
from the router, a 422 from validation, or the limiter's own 429. ``get_db`` is replaced anyway,
so no case can reach a database whatever the route does.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence

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

_MethodPath = tuple[str, str]

_PROBE: _MethodPath = ("POST", "/api/v1/auth/login")

# The routes where an account or a token can be guessed or probed, under the method each is
# served with, and under a method none of them serves, because the count is by path.
_COUNTED: list[_MethodPath] = [
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/onboard"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/forgot-password"),
    ("POST", "/api/v1/auth/resend-verification"),
    ("POST", "/api/v1/invitations/any-token/accept"),
    ("GET", "/api/v1/auth/login"),
    ("PUT", "/api/v1/invitations/another-token/accept"),
    # An encoded "?" or "#" decodes inside the token, where the router still matches accept.
    # Re-parsed as a URL, the same path would end at the token and pass uncounted.
    ("POST", "/api/v1/invitations/any%3Ftoken/accept"),
    ("POST", "/api/v1/invitations/any%23token/accept"),
]

# Signed-in profile routes, where a wrong bearer token is a 401 and a signed token cannot be
# guessed, and paths under either old prefix that name no counted route.
_UNCOUNTED: list[_MethodPath] = [
    ("GET", "/api/v1/auth/me"),
    ("PATCH", "/api/v1/auth/me"),
    ("POST", "/api/v1/auth/me/fcm-token"),
    ("DELETE", "/api/v1/auth/me/fcm-token"),
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/auth/no-such-route"),
    ("POST", "/api/v1/auth/login/extra"),
    ("POST", "/api/v1/invitations/any-token"),
    ("POST", "/api/v1/invitations/any-token/accept/extra"),
]


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


async def _statuses(application: FastAPI, requests: Sequence[_MethodPath]) -> list[int]:
    """Send *requests* in order from one client address, inside one window, and read each."""
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return [
            (await client.request(method, path, json={})).status_code for method, path in requests
        ]


async def test_with_nothing_set_the_21st_request_in_the_window_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production's budget, unchanged by #226: twenty admitted, the twenty-first refused."""
    statuses = await _statuses(_app(monkeypatch, None), [_PROBE] * 21)

    assert 429 not in statuses[:20], statuses
    assert statuses[20] == 429, statuses


async def test_raised_the_same_21st_request_is_admitted_and_the_new_boundary_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raised to 25, the request the default refuses is admitted, and the 26th is refused.

    The second half is what keeps "raised" from passing as "off": a limiter that stopped
    counting would admit the 26th too.
    """
    statuses = await _statuses(_app(monkeypatch, "25"), [_PROBE] * 26)

    assert statuses[20] != 429, statuses
    assert 429 not in statuses[:25], statuses
    assert statuses[25] == 429, statuses


async def test_with_the_budget_spent_on_login_auth_me_is_admitted_and_accept_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#280's reading. Twenty logins spend the bucket, and the next three requests read it.

    The 21st login is refused. ``GET /auth/me`` with no token is answered by the route, 401,
    because the bucket does not count it. Invitation accept is refused, because it shares the
    bucket the logins spent.
    """
    statuses = await _statuses(
        _app(monkeypatch, None),
        [_PROBE] * 20
        + [_PROBE, ("GET", "/api/v1/auth/me"), ("POST", "/api/v1/invitations/any-token/accept")],
    )

    assert statuses[:20] == [422] * 20, statuses
    assert statuses[20:] == [429, 401, 429], statuses


@pytest.mark.parametrize(("method", "path"), _COUNTED, ids=[f"{m} {p}" for m, p in _COUNTED])
async def test_a_counted_request_spends_the_login_bucket_and_is_refused_by_it(
    monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    """Twenty of it spend the budget, so the login after them is refused, and so is it."""
    request = (method, path)
    statuses = await _statuses(_app(monkeypatch, None), [request] * 20 + [_PROBE, request])

    assert 429 not in statuses[:20], statuses
    assert statuses[20:] == [429, 429], statuses


@pytest.mark.parametrize(("method", "path"), _UNCOUNTED, ids=[f"{m} {p}" for m, p in _UNCOUNTED])
async def test_an_uncounted_request_neither_spends_the_bucket_nor_is_refused_by_it(
    monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    """Twenty of it, then twenty logins, then it again, then one more login.

    The twenty logins are all admitted, so the twenty before them spent nothing. The request
    after them is answered by the app, not the limiter, so a full bucket does not refuse it.
    The last login is refused, which shows the bucket really was full when it was admitted.
    """
    request = (method, path)
    statuses = await _statuses(
        _app(monkeypatch, None), [request] * 20 + [_PROBE] * 20 + [request, _PROBE]
    )

    assert 429 not in statuses[:20], statuses
    assert statuses[20:40] == [422] * 20, statuses
    assert statuses[40] == statuses[0], statuses
    assert statuses[41] == 429, statuses


def test_every_route_under_the_old_prefixes_is_in_one_of_the_two_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A route added under ``/api/v1/auth`` or ``/api/v1/invitations`` has to be sorted.

    The two lists above are a setting until something checks them against the app. This reads
    the routes ``create_app()`` serves under either prefix, with ``{token}`` filled in the way
    the lists fill it, and requires each method and path to be in exactly one of them. It does
    not decide which list a new route belongs in. The parametrized cases above read that.

    It reads the OpenAPI schema, because FastAPI 0.141 no longer flattens included routers into
    ``app.routes`` (``test_app_smoke.py``). A route declared with ``include_in_schema=False``
    would not be seen. None under these prefixes is.
    """
    paths = _app(monkeypatch, None).openapi()["paths"]
    served = {
        (method.upper(), re.sub(r"\{[^}]+\}", "any-token", path))
        for path, operations in paths.items()
        if path.startswith(("/api/v1/auth/", "/api/v1/invitations/"))
        for method in operations
    }

    assert served, "no route found under either prefix"
    assert not set(_COUNTED) & set(_UNCOUNTED)
    assert served - set(_COUNTED) - set(_UNCOUNTED) == set()


@pytest.mark.parametrize("value", ["0", "-5"])
def test_a_budget_that_admits_nothing_refuses_to_boot(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Zero or less would answer 429 to every sign-in, so settings refuse it by name."""
    monkeypatch.setenv(_SETTING, value)

    with pytest.raises(ValidationError, match=_SETTING):
        Settings(_env_file=None)
