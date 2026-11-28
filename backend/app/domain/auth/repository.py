"""Repository protocols and read models for the Auth bounded context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.domain.auth.platform_role import PlatformRole


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
    platform_role: PlatformRole = "user"


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

    async def create_clan(self, *, name: str, slug: str) -> uuid.UUID:
        """Create a clan and return its id.

        Builds the ORM row inside the adapter so the application layer never imports
        ``app.models`` (CQRS write side goes through domain + ports)."""
        ...

    def add_membership(
        self,
        *,
        clan_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        is_approved: bool,
        approved_by: uuid.UUID | None = None,
        approved_at: datetime | None = None,
    ) -> None:
        """Stage a user_clan_roles row (approved admin on create, pending viewer on join)."""
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

    async def get_login_profile(self, user_id: uuid.UUID) -> AuthProfileView | None:
        """Login profile (profile + membership + clan, *including* pending roles).

        Lives on the query port, not the write repository: it is a projection
        read — the CQRS rule here is that command handlers load aggregates via
        repositories but read projections via query ports."""
        ...

    async def has_pending_membership(self, user_id: uuid.UUID) -> bool:
        """Whether the user has any pending clan membership."""
        ...

    async def is_account_active(self, user_id: uuid.UUID) -> bool | None:
        """``user_profiles.is_active`` for this user; ``None`` when no profile row exists."""
        ...


class FCMTokenRepository(Protocol):
    """Abstract persistence contract for FCM push token operations."""

    async def register_token(self, user_id: str, token: str, device_platform: str) -> None:
        """Register or update a push token."""
        ...

    async def remove_token(self, user_id: str, token: str) -> None:
        """Remove a push token."""
        ...


@dataclass(frozen=True)
class RemovedRole:
    """One clan role an account held when it was deleted (ADR-079)."""

    clan_id: uuid.UUID
    role: str


class AccountRepository(Protocol):
    """Persistence contract for deleting a user's own account (ADR-079).

    Runs on the privileged session: the account spans every clan it belongs to, and
    ``identity_claims`` is deny-all for the request role."""

    async def lock_clans_where_last_admin(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """Lock the approved-admin rows of every clan this user administers and return
        the clans where this user is the ONLY approved admin, ordered by id."""
        ...

    async def remove_roles(self, user_id: uuid.UUID) -> list[RemovedRole]:
        """Delete every ``user_clan_roles`` row of the user, approved or pending."""
        ...

    async def remove_claims_and_push_tokens(self, user_id: uuid.UUID) -> None:
        """Delete the user's identity claims and push tokens."""
        ...

    async def tombstone_profile(self, user_id: uuid.UUID) -> bool:
        """Clear the profile's personal data and deactivate it, keeping the row so a
        still-valid access token is refused instead of re-provisioning a profile.
        Returns False when there was no live profile to clear."""
        ...
