"""Me use-case handler — clan membership queries."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError


class MeQueryHandler:
    """Read-only handler for current-user clan queries."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_clans(self, *, user_id: str) -> dict[str, Any]:
        """List all approved clan memberships for the user."""
        result = await self._db.execute(
            text(
                "SELECT ucr.clan_id, c.name AS clan_name, c.slug AS clan_slug, "
                "ucr.role, ucr.joined_at "
                "FROM user_clan_roles ucr "
                "JOIN clans c ON c.id = ucr.clan_id "
                "WHERE ucr.user_id = :user_id AND ucr.is_approved = true "
                "ORDER BY ucr.joined_at"
            ),
            {"user_id": user_id},
        )
        rows = result.fetchall()

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
        result = await self._db.execute(
            text(
                "SELECT ucr.clan_id, c.name AS clan_name, c.slug AS clan_slug, "
                "ucr.role "
                "FROM user_clan_roles ucr "
                "JOIN clans c ON c.id = ucr.clan_id "
                "WHERE ucr.user_id = :user_id AND ucr.clan_id = :clan_id "
                "AND ucr.is_approved = true"
            ),
            {"user_id": user_id, "clan_id": str(clan_id)},
        )
        row = result.fetchone()

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
