"""Me use-case handler — clan membership queries."""

from __future__ import annotations

import uuid
from typing import Any

from app.core.exceptions import ForbiddenError
from app.domain.me.query_port import MeQueryPort


class MeQueryHandler:
    """Read-only handler for current-user clan queries."""

    def __init__(self, query_port: MeQueryPort) -> None:
        self._query_port = query_port

    async def list_clans(self, *, user_id: str) -> dict[str, Any]:
        """List all approved clan memberships for the user."""
        rows = await self._query_port.list_clans(user_id)

        return {
            "clans": [
                {
                    "clan_id": str(row.clan_id),
                    "clan_name": row.clan_name,
                    "clan_slug": row.clan_slug,
                    "role": row.role,
                    "joined_at": row.joined_at.isoformat() if row.joined_at else None,
                }
                for row in rows
            ],
            "count": len(rows),
        }

    async def select_clan(self, *, user_id: str, clan_id: uuid.UUID) -> dict[str, Any]:
        """Validate and select a clan as the active context."""
        row = await self._query_port.get_clan_membership(user_id, clan_id)

        if not row:
            raise ForbiddenError("You do not have approved membership in this clan")

        return {
            "clan_id": str(row.clan_id),
            "clan_name": row.clan_name,
            "clan_slug": row.clan_slug,
            "role": row.role,
            "message": (
                "Clan selected. Set X-Current-Clan-Id header to this clan_id on subsequent requests."
            ),
        }
