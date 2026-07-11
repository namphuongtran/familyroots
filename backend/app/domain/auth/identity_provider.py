"""Identity-provider port for the auth context.

Abstracts the external identity provider (Supabase Auth today) so the application
layer depends only on this domain port, never on the concrete SDK. The infrastructure
adapter lives in ``app.infrastructure.supabase_identity_provider``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AuthTokens:
    """An issued session's tokens."""

    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """The result of a successful sign-in: the provider's user + a fresh session."""

    user_id: str
    email: str
    full_name: str
    tokens: AuthTokens


class IdentityError(Exception):
    """Base class for identity-provider failures (provider-agnostic)."""


class IdentityUserExistsError(IdentityError):
    """Raised when creating a user whose email already exists."""


class IdentityAuthError(IdentityError):
    """Raised when credentials / a refresh token are invalid or rejected."""


class IdentityEmailNotVerifiedError(IdentityError):
    """The account exists but its email has not been confirmed yet.

    A distinct sibling of IdentityAuthError (NOT a subclass) so a caller catching
    IdentityAuthError does not swallow it — it propagates to a dedicated 403 handler,
    the same way IdentityUnavailableError propagates to its 503 handler."""


class IdentityUnavailableError(IdentityError):
    """The identity provider could not be reached or is misconfigured.

    Covers DNS/connection/timeout failures, provider 5xx, and rejected *API keys*
    (our configuration) — anything that is NOT the caller's credentials. Surfaced
    as HTTP 503, never as "invalid credentials": conflating the two masked a
    paused project and a wrong service key as user error."""


class IdentityWeakPasswordError(IdentityError):
    """The provider rejected the chosen password as too weak (registration).

    A client input error — surfaced as HTTP 422 "password too weak", never as a 503
    outage (the provider's password policy can be stricter than the app's length check,
    so this is reachable even after local validation)."""


class IdentityProvider(Protocol):
    """What the auth use-cases need from the external identity provider."""

    async def create_user(self, *, email: str, password: str) -> str:
        """Create a user and return its provider id. Raises IdentityUserExistsError
        if the email already exists, IdentityError on other failures."""
        ...

    async def delete_user(self, user_id: str) -> None:
        """Delete a user (used to compensate a failed registration)."""
        ...

    async def sign_in(self, *, email: str, password: str) -> AuthenticatedIdentity:
        """Authenticate with email + password. Raises IdentityAuthError on failure."""
        ...

    async def refresh(self, *, refresh_token: str) -> AuthTokens:
        """Exchange a refresh token for new tokens. Raises IdentityAuthError on failure."""
        ...

    async def sign_out(self, *, access_token: str) -> None:
        """Revoke the session (best-effort; never raises)."""
        ...

    async def update_user(
        self, *, user_id: str, full_name: str | None, preferred_locale: str | None
    ) -> None:
        """Update provider-side user metadata (full_name / preferred_locale)."""
        ...

    async def send_password_reset(self, *, email: str) -> None:
        """Best-effort: send a password-reset (recovery) email via the provider.

        Completion (verifying the recovery token + setting the new password) happens
        client-side via the provider SDK — this only triggers the email."""
        ...

    async def send_verification_email(self, *, email: str) -> None:
        """Best-effort: (re)send the signup email-verification link via the provider.

        Confirmation completes via the provider's hosted flow + the configured
        redirect target — this only triggers the email."""
        ...
