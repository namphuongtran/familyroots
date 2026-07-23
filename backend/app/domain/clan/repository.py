"""Repository protocol for the Clan bounded context."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from app.domain.clan.entity import Clan


class ClanRepository(Protocol):
    """Abstract persistence contract for Clan operations."""

    async def get_clan(self, clan_id: uuid.UUID) -> Any | None:
        """Get clan ORM model by ID (read side — feeds response serialization)."""
        ...

    async def get_clan_for_update(self, clan_id: uuid.UUID) -> Clan | None:
        """Load the Clan aggregate for a write, or None if it does not exist."""
        ...

    async def save_clan(self, clan: Clan) -> Any:
        """Persist a mutated Clan aggregate onto its ORM row; returns the ORM model."""
        ...

    async def get_user_clan_role(self, clan_id: uuid.UUID, user_id: uuid.UUID) -> Any | None:
        """Get a user's clan role record."""
        ...

    async def lock_admin_count(self, clan_id: uuid.UUID) -> int:
        """Lock the clan's approved-admin rows FOR UPDATE and return their count."""
        ...

    async def list_users(
        self,
        clan_id: uuid.UUID,
        approved: bool = True,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[Any], bool]:
        """List users with pagination. Returns (items, has_next)."""
        ...

    async def get_clan_stats(self, clan_id: uuid.UUID) -> dict[str, int]:
        """Get aggregate statistics for a clan."""
        ...

    async def approve_user(self, ucr: Any, approved_by: uuid.UUID) -> None:
        """Approve a pending user."""
        ...

    async def delete_user_role(self, ucr: Any) -> None:
        """Delete a user clan role record."""
        ...

    async def change_role(self, ucr: Any, new_role: str) -> None:
        """Change a user's role."""
        ...

    async def get_membership_with_person(
        self, clan_id: uuid.UUID, person_id: uuid.UUID
    ) -> Any | None:
        """Membership row for a LIVE person of this clan (persons.is_deleted = false)."""
        ...

    async def get_founder_membership(self, clan_id: uuid.UUID) -> Any | None:
        """The clan's current founder membership row, if any."""
        ...
