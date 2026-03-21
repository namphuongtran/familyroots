"""SQLAlchemy implementations for Platform Admin bounded context."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import build_page, paginate_query
from app.domain.platform_admin.query_port import PlatformAdminQueryPort
from app.models.audit_log import AuditLog
from app.models.clan import Clan
from app.models.clan_membership import ClanMembership
from app.models.person import Person
from app.models.user_clan_role import UserClanRole


class SqlAlchemyPlatformAdminQueryPort(PlatformAdminQueryPort):
    """SQLAlchemy implementation of Platform Admin read persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_clans(self, cursor: str | None, limit: int) -> dict[str, Any]:
        query = select(Clan)
        query = paginate_query(query, Clan, cursor, limit)
        result = await self._session.execute(query)
        clans = list(result.scalars().all())

        page = build_page(clans, limit)
        page["data"] = [
            {
                "id": str(c.id),
                "name": c.name,
                "slug": c.slug,
                "is_active": c.is_active,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in page["data"]
        ]
        return page

    async def get_clan_detail(self, clan_id: uuid.UUID) -> dict[str, Any]:
        result = await self._session.execute(select(Clan).where(Clan.id == clan_id))
        clan = result.scalar_one_or_none()
        if not clan:
            raise NotFoundError("clan_not_found")

        stats_result = await self._session.execute(
            select(
                func.count(func.distinct(ClanMembership.id)).label("total_members"),
                func.count(func.distinct(UserClanRole.id)).label("total_users"),
            )
            .select_from(ClanMembership)
            .outerjoin(UserClanRole, UserClanRole.clan_id == ClanMembership.clan_id)
            .where(ClanMembership.clan_id == clan_id)
        )
        stats = stats_result.one()

        return {
            "id": str(clan.id),
            "name": clan.name,
            "slug": clan.slug,
            "is_active": clan.is_active,
            "description": clan.description,
            "origin_place": clan.origin_place,
            "created_at": clan.created_at.isoformat() if clan.created_at else None,
            "stats": {
                "total_members": stats.total_members or 0,
                "total_users": stats.total_users or 0,
            },
        }

    async def get_metrics(self) -> dict[str, Any]:
        total_clans = select(func.count()).select_from(Clan).scalar_subquery()
        active_clans = (
            select(func.count())
            .select_from(Clan)
            .where(Clan.is_active.is_(True))
            .scalar_subquery()
        )
        total_members = (
            select(func.count())
            .select_from(Person)
            .where(Person.is_deleted.is_(False))
            .scalar_subquery()
        )
        total_users = select(func.count()).select_from(UserClanRole).scalar_subquery()

        result = await self._session.execute(
            select(
                total_clans.label("total_clans"),
                active_clans.label("active_clans"),
                total_members.label("total_members"),
                total_users.label("total_users"),
            )
        )
        row = result.one()

        return {
            "total_clans": row.total_clans or 0,
            "active_clans": row.active_clans or 0,
            "suspended_clans": (row.total_clans or 0) - (row.active_clans or 0),
            "total_members": row.total_members or 0,
            "total_users": row.total_users or 0,
        }

    async def get_audit_log(
        self,
        clan_id: uuid.UUID | None,
        action: str | None,
        cursor: str | None,
        limit: int,
    ) -> dict[str, Any]:
        query = select(AuditLog)
        if clan_id:
            query = query.where(AuditLog.clan_id == clan_id)
        if action:
            query = query.where(AuditLog.action == action)

        query = paginate_query(query, AuditLog, cursor, limit)
        result = await self._session.execute(query)
        entries = list(result.scalars().all())

        page = build_page(entries, limit)
        page["data"] = [
            {
                "id": str(e.id),
                "clan_id": str(e.clan_id),
                "actor_id": str(e.actor_id),
                "actor_role": e.actor_role,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": str(e.resource_id) if e.resource_id else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in page["data"]
        ]
        return page
