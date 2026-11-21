"""DB-free auth-session service: refresh, logout, profile metadata."""

from __future__ import annotations

from typing import Any

from app.domain.auth.identity_provider import IdentityAuthError, IdentityProvider
from app.domain.shared.exceptions import AuthenticationError


class AuthSessionService:
    """Auth operations that do NOT require a database session — refresh, logout,
    profile metadata. Depends only on the IdentityProvider port (no SDK import)."""

    def __init__(self, identity: IdentityProvider) -> None:
        self._identity = identity

    async def refresh_token(self, *, refresh_token: str) -> dict[str, Any]:
        """Exchange a refresh token for a new access token."""
        try:
            tokens = await self._identity.refresh(refresh_token=refresh_token)
        except IdentityAuthError as exc:
            raise AuthenticationError("auth.invalid_refresh_token") from exc
        return {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_in": tokens.expires_in,
        }

    async def logout(self, *, access_token: str) -> None:
        """Revoke the user's session (best-effort; the stateless access token
        remains valid until its short expiry)."""
        await self._identity.sign_out(access_token=access_token)

    async def update_profile(
        self, *, user_sub: str, full_name: str | None, preferred_locale: str | None
    ) -> None:
        """Update provider-side user metadata."""
        await self._identity.update_user(
            user_id=user_sub, full_name=full_name, preferred_locale=preferred_locale
        )

    async def send_password_reset(self, *, email: str) -> None:
        """Trigger a provider password-reset email (best-effort)."""
        await self._identity.send_password_reset(email=email)

    async def send_verification_email(self, *, email: str) -> None:
        """Trigger a provider email-verification (best-effort)."""
        await self._identity.send_verification_email(email=email)
