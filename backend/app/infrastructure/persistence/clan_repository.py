"""SQLAlchemy implementation of ClanRepository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import build_page, paginate_query
from app.models.clan import Clan
from app.models.clan_membership import ClanMembership
from app.models.user_clan_role import UserClanRole


class SqlAlchemyClanRepository:
    """ClanRepository backed by SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_clan(self, clan_id: uuid.UUID) -> Clan | None:
        return await self._session.get(Clan, clan_id)

    async def get_user_clan_role(
        self, clan_id: uuid.UUID, user_id: uuid.UUID
    ) -> UserClanRole | None:
        result = await self._session.execute(
            select(UserClanRole).where(
                UserClanRole.clan_id == clan_id, UserClanRole.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def count_admins(self, clan_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count()).where(
                UserClanRole.clan_id == clan_id,
                UserClanRole.role == "admin",
                UserClanRole.is_approved.is_(True),
            )
        )
        return result.scalar() or 0

    async def list_users(
        self,
        clan_id: uuid.UUID,
        approved: bool = True,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List users with pagination. Returns a page dict."""
        query = select(UserClanRole).where(
            UserClanRole.clan_id == clan_id,
            UserClanRole.is_approved.is_(approved),
        )
        capped = min(limit, 100)
        query = paginate_query(query, UserClanRole, cursor, capped)
        result = await self._session.execute(query)
        items = list(result.scalars().all())
        return build_page(items, capped)

    async def get_clan_stats(self, clan_id: uuid.UUID) -> dict[str, int]:
        total_users_result = await self._session.execute(
            select(func.count()).where(UserClanRole.clan_id == clan_id)
        )
        approved_users_result = await self._session.execute(
            select(func.count()).where(
                UserClanRole.clan_id == clan_id,
                UserClanRole.is_approved.is_(True),
            )
        )
        pending_users_result = await self._session.execute(
            select(func.count()).where(
                UserClanRole.clan_id == clan_id,
                UserClanRole.is_approved.is_(False),
            )
        )
        total_members_result = await self._session.execute(
            select(func.count()).where(ClanMembership.clan_id == clan_id)
        )

        return {
            "total_users": total_users_result.scalar() or 0,
            "approved_users": approved_users_result.scalar() or 0,
            "pending_users": pending_users_result.scalar() or 0,
            "total_members": total_members_result.scalar() or 0,
        }

    async def update_clan(self, clan_id: uuid.UUID, changes: dict[str, object]) -> Clan:
        clan = await self._session.get(Clan, clan_id)
        for field, value in changes.items():
            setattr(clan, field, value)
        return clan

    async def approve_user(self, ucr: UserClanRole, approved_by: uuid.UUID) -> None:
        ucr.is_approved = True
        ucr.approved_by = approved_by
        ucr.approved_at = datetime.now(UTC)

    async def delete_user_role(self, ucr: UserClanRole) -> None:
        await self._session.delete(ucr)

    async def change_role(self, ucr: UserClanRole, new_role: str) -> None:
        ucr.role = new_role
