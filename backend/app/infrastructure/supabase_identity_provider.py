"""Supabase implementation of the auth IdentityProvider port.

Wraps the Supabase Auth SDK and translates its (string-y, SDK-specific) failures
into the provider-agnostic domain exceptions, so the application layer never sees
the SDK. The Supabase client is synchronous; these async methods wrap it directly
(pre-existing behavior — the call is short).
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from app.domain.auth.identity_provider import (
    AuthenticatedIdentity,
    AuthTokens,
    IdentityAuthError,
    IdentityError,
    IdentityUserExistsError,
)
from app.infrastructure.supabase_client import get_anon_client, get_service_client


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
            raise IdentityError(str(exc)) from exc
        return str(resp.user.id)

    async def delete_user(self, user_id: str) -> None:
        get_service_client().auth.admin.delete_user(user_id)

    async def sign_in(self, *, email: str, password: str) -> AuthenticatedIdentity:
        sb = get_anon_client()
        try:
            resp = sb.auth.sign_in_with_password({"email": email, "password": password})
        except Exception as exc:
            raise IdentityAuthError() from exc
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
            raise IdentityAuthError() from exc
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
