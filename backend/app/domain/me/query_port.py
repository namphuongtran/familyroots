"""Query port protocols for Me bounded context."""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class MeQueryPort(Protocol):
    """Abstract persistence contract for Me read operations."""

    async def list_clans(self, user_id: str) -> list[Any]:
        """List all approved clan memberships for the user."""
        ...

    async def get_clan_membership(self, user_id: str, clan_id: uuid.UUID) -> Any | None:
        """Get approved membership for a specific clan."""
        ...
