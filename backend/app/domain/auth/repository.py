"""Repository protocols for Auth bounded context."""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class AuthRepository(Protocol):
    """Abstract persistence contract for Auth write operations."""

    async def get_clan_by_slug(self, slug: str) -> Any | None:
        """Get clan by slug."""
        ...

    async def get_clan_by_id(self, clan_id: uuid.UUID) -> Any | None:
        """Get clan by ID."""
        ...

    def add_clan(self, clan: Any) -> None:
        """Add a new clan to persistence context."""
        ...

    def add_user_role(self, role: Any) -> None:
        """Add a new user clan role to persistence context."""
        ...


class AuthQueryPort(Protocol):
    """Abstract persistence contract for Auth read operations."""

    async def get_profile(self, user_id: uuid.UUID) -> Any | None:
        """Get approved profile for a user ID."""
        ...

    async def get_login_profile(self, user_id: uuid.UUID) -> Any | None:
        """Get initial login profile for a user ID (including pending roles)."""
        ...


class FCMTokenRepository(Protocol):
    """Abstract persistence contract for FCM push token operations."""

    async def register_token(self, user_id: str, token: str, device_platform: str) -> None:
        """Register or update a push token."""
        ...

    async def remove_token(self, user_id: str, token: str) -> None:
        """Remove a push token."""
        ...
