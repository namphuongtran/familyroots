"""Repository protocol for the Clan bounded context."""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class ClanRepository(Protocol):
    """Abstract persistence contract for Clan operations."""

    async def get_clan(self, clan_id: uuid.UUID) -> Any | None:
        """Get clan ORM model by ID."""
        ...

    async def get_user_clan_role(self, clan_id: uuid.UUID, user_id: uuid.UUID) -> Any | None:
        """Get a user's clan role record."""
        ...

    async def count_admins(self, clan_id: uuid.UUID) -> int:
        """Count approved admins in a clan."""
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

    async def update_clan(self, clan_id: uuid.UUID, changes: dict[str, object]) -> Any:
        """Apply changes to a clan record."""
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
