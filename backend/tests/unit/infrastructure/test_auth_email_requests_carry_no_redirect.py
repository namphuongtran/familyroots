"""Neither auth email the backend asks GoTrue to send carries a redirect (#202, ADR-063 § 4).

The two templates in ``supabase/templates/`` build their link from ``{{ .SiteURL }}`` and ignore
``{{ .RedirectTo }}``, so the two redirect settings ADR-063 § 4 names were deleted with #202.
What is read here is the request itself: a real ``supabase_auth`` client sends both calls
through an ``httpx.MockTransport``, and the test reads the method, the path and the query GoTrue
would receive. GoTrue takes the redirect from the ``redirect_to`` query parameter
(``gotrue_base_api.py`` ``_request`` in supabase_auth 2.31.0).
"""

import json
from types import SimpleNamespace

import httpx
import pytest

# The package re-exports it, but without `as`, so mypy's no_implicit_reexport refuses that path.
from supabase_auth._sync.gotrue_client import SyncGoTrueClient

import app.infrastructure.supabase_identity_provider as mod


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    auth = SyncGoTrueClient(
        url="http://gotrue.test/auth/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(answer)),
    )
    monkeypatch.setattr(mod, "get_anon_client", lambda: SimpleNamespace(auth=auth))
    return requests


async def test_the_recovery_email_request_carries_no_redirect(sent: list[httpx.Request]) -> None:
    await mod.SupabaseIdentityProvider().send_password_reset(email="a@example.com")

    [request] = sent
    assert (request.method, request.url.path) == ("POST", "/auth/v1/recover")
    assert "redirect_to" not in request.url.params
    assert json.loads(request.content)["email"] == "a@example.com"


async def test_the_confirmation_email_request_carries_no_redirect(
    sent: list[httpx.Request],
) -> None:
    await mod.SupabaseIdentityProvider().send_verification_email(email="a@example.com")

    [request] = sent
    assert (request.method, request.url.path) == ("POST", "/auth/v1/resend")
    assert "redirect_to" not in request.url.params
    body = json.loads(request.content)
    assert (body["type"], body["email"]) == ("signup", "a@example.com")
