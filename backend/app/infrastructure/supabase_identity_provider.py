"""Supabase implementation of the auth IdentityProvider port.

Wraps the Supabase Auth SDK and translates its (string-y, SDK-specific) failures
into the provider-agnostic domain exceptions, so the application layer never sees
the SDK. The Supabase client is synchronous; these async methods wrap it directly
(pre-existing behavior — the call is short).
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from supabase_auth.errors import AuthApiError, AuthRetryableError, AuthWeakPasswordError

from app.core.config import settings
from app.domain.auth.identity_provider import (
    AuthenticatedIdentity,
    AuthTokens,
    IdentityAuthError,
    IdentityError,
    IdentityUnavailableError,
    IdentityUserExistsError,
    IdentityWeakPasswordError,
)
from app.infrastructure.supabase_client import get_anon_client, get_service_client


def _classify(exc: Exception) -> IdentityError:
    """Map an SDK/transport failure to the right domain exception.

    Only a definitive API rejection of the *user's* credentials becomes
    ``IdentityAuthError``. Everything infrastructural — network/DNS/timeout (the
    request never reached the provider), provider 5xx, or a rejected *API key*
    (our configuration) — becomes ``IdentityUnavailableError`` so callers surface
    503 instead of lying "invalid credentials"."""
    if isinstance(exc, AuthWeakPasswordError):
        # A too-weak password on registration is a client input error, not an outage
        # and not "invalid credentials" — surface it as 422, not 503 (it extends
        # CustomAuthError, so without this it would fall through to the 503 catch-all).
        return IdentityWeakPasswordError(str(exc))
    if isinstance(exc, AuthRetryableError):
        return IdentityUnavailableError(str(exc))
    if isinstance(exc, AuthApiError):
        if "api key" in str(exc).lower():
            return IdentityUnavailableError(str(exc))
        # Provider 5xx, plus 429 (rate limited) and 408 (request timeout), are
        # transient/infrastructural — NOT a verdict on the user's credentials. Mapping
        # them to IdentityAuthError would lie "invalid credentials" (401) when the truth
        # is "try again later" (503). Only the remaining 4xx (a real invalid-credentials
        # rejection) becomes IdentityAuthError.
        if exc.status >= 500 or exc.status in (408, 429):
            return IdentityUnavailableError(str(exc))
        return IdentityAuthError()
    # Non-HTTP failure (DNS, connection refused, TLS, timeout): never reached
    # the provider.
    return IdentityUnavailableError(str(exc))


class SupabaseIdentityProvider:
    """IdentityProvider backed by Supabase Auth."""

    async def create_user(self, *, email: str, password: str) -> str:
        sb = get_service_client()
        try:
            resp = sb.auth.admin.create_user(
                {"email": email, "password": password, "email_confirm": True}
            )
        except Exception as exc:
            if "already" in str(exc).lower():
                raise IdentityUserExistsError() from exc
            classified = _classify(exc)
            # Preserve the specific verdict (503 outage / 422 weak password); only an
            # otherwise-unclassified failure collapses to the generic IdentityError.
            if isinstance(classified, IdentityUnavailableError | IdentityWeakPasswordError):
                raise classified from exc
            raise IdentityError(str(exc)) from exc
        return str(resp.user.id)

    async def delete_user(self, user_id: str) -> None:
        get_service_client().auth.admin.delete_user(user_id)

    async def sign_in(self, *, email: str, password: str) -> AuthenticatedIdentity:
        sb = get_anon_client()
        try:
            resp = sb.auth.sign_in_with_password({"email": email, "password": password})
        except Exception as exc:
            raise _classify(exc) from exc
        if resp.session is None or resp.user is None:
            raise IdentityAuthError()
        return AuthenticatedIdentity(
            user_id=str(resp.user.id),
            email=email,
            full_name=resp.user.user_metadata.get("full_name", ""),
            tokens=AuthTokens(
                access_token=resp.session.access_token,
                refresh_token=resp.session.refresh_token,
                expires_in=resp.session.expires_in,
            ),
        )

    async def refresh(self, *, refresh_token: str) -> AuthTokens:
        sb = get_anon_client()
        try:
            resp = sb.auth.refresh_session(refresh_token)
        except Exception as exc:
            raise _classify(exc) from exc
        if resp.session is None:
            raise IdentityAuthError()
        return AuthTokens(
            access_token=resp.session.access_token,
            refresh_token=resp.session.refresh_token,
            expires_in=resp.session.expires_in,
        )

    async def sign_out(self, *, access_token: str) -> None:
        # Best-effort: the stateless access token remains valid until its short
        # expiry; this just prevents the session from being renewed.
        with suppress(Exception):
            get_service_client().auth.admin.sign_out(access_token, "global")

    async def update_user(
        self, *, user_id: str, full_name: str | None, preferred_locale: str | None
    ) -> None:
        update_data: dict[str, Any] = {}
        if full_name is not None:
            update_data["user_metadata"] = {"full_name": full_name}
        if preferred_locale is not None:
            update_data.setdefault("user_metadata", {})["preferred_locale"] = preferred_locale
        if update_data:
            # The SDK types this as AdminUserAttributes but accepts a dict at runtime
            # (matches the prior implementation).
            get_service_client().auth.admin.update_user_by_id(user_id, update_data)  # type: ignore[arg-type]

    async def send_password_reset(self, *, email: str) -> None:
        # Anon client (no service role needed); off-loaded — the SDK call is blocking.
        # Pass redirect_to only when configured; otherwise Supabase uses the project
        # Site URL. Completion is client-side (verify_otp recovery + update_user).
        opts: dict[str, Any] = {}
        if settings.PASSWORD_RESET_REDIRECT_URL:
            opts["redirect_to"] = settings.PASSWORD_RESET_REDIRECT_URL
        # The SDK types `options` as its `Options` TypedDict but accepts a plain dict
        # at runtime (same pattern as update_user_by_id above).
        await asyncio.to_thread(
            get_anon_client().auth.reset_password_email,
            email,
            opts,  # type: ignore[arg-type]
        )
