"""SQLAlchemy implementations for Me bounded context."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.me.query_port import MeQueryPort


class SqlAlchemyMeQueryPort(MeQueryPort):
    """SQLAlchemy implementation of Me read persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_clans(self, user_id: str) -> list[Any]:
        result = await self._session.execute(
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
        return list(result.fetchall())

    async def get_clan_membership(self, user_id: str, clan_id: uuid.UUID) -> Any | None:
        result = await self._session.execute(
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
        return result.fetchone()
