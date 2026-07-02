"""SQLAlchemy implementations for Me bounded context."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.me.query_port import ClanMembershipView, MeQueryPort


class SqlAlchemyMeQueryPort(MeQueryPort):
    """SQLAlchemy implementation of Me read persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_clans(self, user_id: str) -> list[ClanMembershipView]:
        result = await self._session.execute(
            text(
                # user_clan_roles has no joined_at column; created_at is the row's
                # creation time, i.e. when the membership was established.
                "SELECT ucr.clan_id, c.name AS clan_name, c.slug AS clan_slug, "
                "ucr.role, ucr.created_at AS joined_at "
                "FROM user_clan_roles ucr "
                "JOIN clans c ON c.id = ucr.clan_id "
                "WHERE ucr.user_id = :user_id AND ucr.is_approved = true "
                "ORDER BY ucr.created_at"
            ),
            {"user_id": user_id},
        )
        return [
            ClanMembershipView(
                clan_id=row["clan_id"],
                clan_name=row["clan_name"],
                clan_slug=row["clan_slug"],
                role=row["role"],
                joined_at=row["joined_at"],
            )
            for row in result.mappings()
        ]

    async def get_clan_membership(
        self, user_id: str, clan_id: uuid.UUID
    ) -> ClanMembershipView | None:
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
        row = result.mappings().first()
        if row is None:
            return None
        return ClanMembershipView(
            clan_id=row["clan_id"],
            clan_name=row["clan_name"],
            clan_slug=row["clan_slug"],
            role=row["role"],
        )
