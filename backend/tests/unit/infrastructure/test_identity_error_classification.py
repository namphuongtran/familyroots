"""Identity-provider failures must be classified truthfully.

Regression for the debugging trap on main: sign_in/refresh mapped ANY exception
to IdentityAuthError → 401 "invalid credentials", so a paused Supabase project
(DNS NXDOMAIN) and a wrong service key both looked like a wrong password. Only a
definitive credential rejection may be IdentityAuthError; infrastructure failures
must be IdentityUnavailableError (→ 503).
"""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from supabase_auth.errors import AuthApiError, AuthRetryableError, AuthWeakPasswordError

from app.application.auth.handlers import AuthCommandHandler
from app.domain.auth.identity_provider import (
    IdentityAuthError,
    IdentityUnavailableError,
    IdentityWeakPasswordError,
)
from app.domain.shared.exceptions import ValidationError
from app.infrastructure import supabase_identity_provider as sip


def _repo_with_slug_free() -> AsyncMock:
    """register() now validates clan input (incl. the slug-taken check) up front,
    before create_user — so these identity-error-classification tests (which only
    care about what happens after create_user is invoked) need a repo double
    that answers get_clan_by_slug like a real async repository (slug not taken),
    rather than ``None``."""
    repo = AsyncMock()
    repo.get_clan_by_slug.return_value = None
    return repo


class _RaisingAuth:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def sign_in_with_password(self, *_a: Any, **_k: Any) -> Any:
        raise self._exc

    def refresh_session(self, *_a: Any, **_k: Any) -> Any:
        raise self._exc


class _RaisingClient:
    def __init__(self, exc: Exception) -> None:
        self.auth = _RaisingAuth(exc)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        # Definitive credential rejection from the API → auth error (401).
        (AuthApiError("Invalid login credentials", 400, None), IdentityAuthError),
        # Rejected API key is OUR configuration, not the user's credentials.
        (AuthApiError("Invalid API key", 401, None), IdentityUnavailableError),
        # Provider-side failure.
        (AuthApiError("upstream exploded", 502, None), IdentityUnavailableError),
        (AuthRetryableError("timeout", 503), IdentityUnavailableError),
        # Rate limited / upstream timeout are transient, not "wrong password" → 503.
        (AuthApiError("Too Many Requests", 429, None), IdentityUnavailableError),
        (AuthApiError("Request Timeout", 408, None), IdentityUnavailableError),
        # Transport failure — request never reached the provider (paused project
        # DNS NXDOMAIN surfaced exactly like this).
        (ConnectionError("[Errno -2] Name or service not known"), IdentityUnavailableError),
    ],
)
@pytest.mark.asyncio
async def test_sign_in_classifies_failures(
    monkeypatch: pytest.MonkeyPatch, exc: Exception, expected: type[Exception]
) -> None:
    monkeypatch.setattr(sip, "get_anon_client", lambda: _RaisingClient(exc))
    with pytest.raises(expected):
        await sip.SupabaseIdentityProvider().sign_in(email="a@b.c", password="x")


@pytest.mark.asyncio
async def test_refresh_classifies_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sip, "get_anon_client", lambda: _RaisingClient(ConnectionError("refused")))
    with pytest.raises(IdentityUnavailableError):
        await sip.SupabaseIdentityProvider().refresh(refresh_token="rt")


class _RaisingAdmin:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def create_user(self, *_a: Any, **_k: Any) -> Any:
        raise self._exc


class _RaisingServiceClient:
    def __init__(self, exc: Exception) -> None:
        self.auth = type("_A", (), {"admin": _RaisingAdmin(exc)})()


@pytest.mark.asyncio
async def test_create_user_rate_limit_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_user has its OWN wrapping (re-raises only IdentityUnavailableError, else
    downgrades to a generic IdentityError) — pin that a 429 flows through as 503, not a
    swallowed generic error, across this distinct call site."""
    monkeypatch.setattr(
        sip,
        "get_service_client",
        lambda: _RaisingServiceClient(AuthApiError("Too Many Requests", 429, None)),
    )
    with pytest.raises(IdentityUnavailableError):
        await sip.SupabaseIdentityProvider().create_user(email="a@b.c", password="x")


@pytest.mark.asyncio
async def test_create_user_weak_password_is_not_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A too-weak password is a client input error, not a 503 outage. AuthWeakPasswordError
    extends CustomAuthError (not AuthApiError), so without explicit handling it fell through
    _classify to the Unavailable catch-all."""
    monkeypatch.setattr(
        sip,
        "get_service_client",
        lambda: _RaisingServiceClient(
            AuthWeakPasswordError("Password is too weak", 422, ["length"])
        ),
    )
    with pytest.raises(IdentityWeakPasswordError):
        await sip.SupabaseIdentityProvider().create_user(email="a@b.c", password="weak")


class _UnavailableIdentity:
    async def create_user(self, *, email: str, password: str) -> str:
        raise IdentityUnavailableError("provider down")


@pytest.mark.asyncio
async def test_register_does_not_swallow_unavailable_into_422() -> None:
    """IdentityUnavailableError extends IdentityError — register must re-raise it
    (→ the global 503 handler), not convert it to 422 registration_failed."""
    handler = AuthCommandHandler(
        repo=_repo_with_slug_free(),
        uow=None,  # type: ignore[arg-type]
        identity=_UnavailableIdentity(),  # type: ignore[arg-type]  # stub: only create_user is used
        query_port=None,  # type: ignore[arg-type]
    )
    with pytest.raises(IdentityUnavailableError):
        await handler.register(
            email="a@b.c",
            password="12345678",
            full_name="T",
            clan_action="create",
            clan_name="C",
            clan_slug="c",
        )


def test_email_not_confirmed_maps_to_email_not_verified() -> None:
    from supabase_auth.errors import AuthApiError

    from app.domain.auth.identity_provider import IdentityEmailNotVerifiedError
    from app.infrastructure.supabase_identity_provider import _classify

    exc = AuthApiError("Email not confirmed", 400, "email_not_confirmed")
    assert isinstance(_classify(exc), IdentityEmailNotVerifiedError)


def test_generic_400_still_maps_to_auth_error() -> None:
    from supabase_auth.errors import AuthApiError

    from app.domain.auth.identity_provider import IdentityAuthError
    from app.infrastructure.supabase_identity_provider import _classify

    exc = AuthApiError("Invalid login credentials", 400, "invalid_credentials")
    assert isinstance(_classify(exc), IdentityAuthError)


class _WeakPasswordIdentity:
    async def create_user(self, *, email: str, password: str) -> str:
        raise IdentityWeakPasswordError("Password is too weak")


@pytest.mark.asyncio
async def test_register_maps_weak_password_to_422() -> None:
    """A provider weak-password rejection surfaces as a 422 with the specific
    auth.password_too_weak code — not a 503, and not the generic registration_failed."""
    handler = AuthCommandHandler(
        repo=_repo_with_slug_free(),
        uow=None,  # type: ignore[arg-type]
        identity=_WeakPasswordIdentity(),  # type: ignore[arg-type]  # stub: only create_user is used
        query_port=None,  # type: ignore[arg-type]
    )
    with pytest.raises(ValidationError) as exc:
        await handler.register(
            email="a@b.c",
            password="12345678",
            full_name="T",
            clan_action="create",
            clan_name="C",
            clan_slug="c",
        )
    assert exc.value.code == "auth.password_too_weak"
