"""Vercel Cron reaches the cron routes through the deployment's own hostname (#265).

Measured 2026-10-10. ``vercel crons run /internal/cron/document-purge`` requested
``familyroots-9xtnrccz1-namtp.vercel.app``, the production deployment's generated URL, not
the ``familyroots-api.vercel.app`` alias that ``ALLOWED_HOSTS`` names. The function log
read ``400`` for that request. ``TrustedHostMiddleware`` refused it before any route ran, so
neither scheduled job would ever have run. Vercel exposes that hostname to the function
as ``VERCEL_URL``, and ``Settings.trusted_hosts`` adds it.

Each case builds the real app with ``create_app`` and reads what a request with a given
``Host`` gets: the route's own 404 envelope when the host is trusted, or Starlette's bare
``400 Invalid host header`` when it is not. The lifespan does not run, because the client
is not entered as a context manager.

Negative control, 2026-10-10: with ``main.py`` back on ``settings.ALLOWED_HOSTS``, the
deployment-host case reads ``(400, 'Invalid host header')``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.core.config import settings

pytestmark = [pytest.mark.unit]

_ALIAS = "familyroots-api.vercel.app"
_DEPLOYMENT = "familyroots-9xtnrccz1-namtp.vercel.app"
_UNKNOWN = "someone-else.vercel.app"


def _answer(host: str) -> tuple[int, str]:
    client = TestClient(main_module.create_app(), base_url=f"https://{host}")
    response = client.get("/internal/no-such-route")
    return response.status_code, response.text if response.status_code == 400 else "app"


@pytest.fixture()
def on_vercel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", [_ALIAS])
    monkeypatch.setattr(settings, "VERCEL_URL", _DEPLOYMENT)


@pytest.mark.usefixtures("on_vercel")
def test_the_deployment_host_reaches_the_app_and_an_unknown_host_does_not() -> None:
    assert {host: _answer(host) for host in (_ALIAS, _DEPLOYMENT, _UNKNOWN)} == {
        _ALIAS: (404, "app"),
        _DEPLOYMENT: (404, "app"),
        _UNKNOWN: (400, "Invalid host header"),
    }


def test_without_vercel_url_only_the_listed_hosts_are_trusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", [_ALIAS])
    monkeypatch.setattr(settings, "VERCEL_URL", "")
    assert _answer(_DEPLOYMENT) == (400, "Invalid host header")
    assert _answer(_ALIAS) == (404, "app")


@pytest.mark.parametrize("given", [f"https://{_DEPLOYMENT}", f"{_DEPLOYMENT}/", f" {_DEPLOYMENT} "])
def test_a_scheme_or_a_slash_on_vercel_url_still_names_the_host(
    monkeypatch: pytest.MonkeyPatch, given: str
) -> None:
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", [_ALIAS])
    monkeypatch.setattr(settings, "VERCEL_URL", given)
    assert _answer(_DEPLOYMENT) == (404, "app")
