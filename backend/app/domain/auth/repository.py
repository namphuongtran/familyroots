"""Repository protocols and read models for the Auth bounded context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AuthProfileView:
    """Flattened profile + membership + clan read model.

    Replaces the raw SQLAlchemy ``Row`` that used to cross this seam — handlers
    consume typed fields instead of ``row.<MappedClassName>`` attribute access
    (which silently depends on ORM class names and broke at runtime).
    ``clan_id``/``clan_name``/``role`` are None when the user has no membership.
    """

    person_id: uuid.UUID | None = None
    clan_id: uuid.UUID | None = None
    clan_name: str | None = None
    role: str | None = None
    is_approved: bool = False


class AuthRepository(Protocol):
    """Abstract persistence contract for Auth write operations."""

    async def get_clan_by_slug(self, slug: str) -> Any | None:
        """Get clan by slug."""
        ...

    async def get_clan_by_id(self, clan_id: uuid.UUID) -> Any | None:
        """Get clan by ID."""
        ...

    async def get_user_role(self, user_id: uuid.UUID, clan_id: uuid.UUID) -> Any | None:
        """Get an existing membership for a user in a clan."""
        ...

    async def get_login_profile(self, user_id: uuid.UUID) -> AuthProfileView | None:
        """Get the login profile (profile + membership + clan, incl. pending roles)."""
        ...

    def add_clan(self, clan: Any) -> None:
        """Add a new clan to persistence context."""
        ...

    def add_user_role(self, role: Any) -> None:
        """Add a new user clan role to persistence context."""
        ...

    async def ensure_profile(
        self, user_id: uuid.UUID, email: str, display_name: str | None
    ) -> None:
        """Idempotently ensure a user_profiles row exists for this user."""
        ...


class AuthQueryPort(Protocol):
    """Abstract persistence contract for Auth read operations."""

    async def get_profile(self, user_id: uuid.UUID) -> AuthProfileView | None:
        """Get approved profile for a user ID."""
        ...

    async def has_pending_membership(self, user_id: uuid.UUID) -> bool:
        """Whether the user has any pending clan membership."""
        ...


class FCMTokenRepository(Protocol):
    """Abstract persistence contract for FCM push token operations."""

    async def register_token(self, user_id: str, token: str, device_platform: str) -> None:
        """Register or update a push token."""
        ...

    async def remove_token(self, user_id: str, token: str) -> None:
        """Remove a push token."""
        ...
