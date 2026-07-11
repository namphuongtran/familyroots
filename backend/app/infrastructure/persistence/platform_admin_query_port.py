"""SQLAlchemy implementations for Platform Admin bounded context."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import build_page, paginate_query
from app.domain.platform_admin.query_port import (
    AuditLogEntryView,
    ClanDetailView,
    ClanStatsView,
    ClanSummaryView,
    Page,
    PageMeta,
    PlatformAdminQueryPort,
    PlatformMetricsView,
)
from app.models.audit_log import AuditLog
from app.models.clan import Clan
from app.models.clan_membership import ClanMembership
from app.models.person import Person
from app.models.user_clan_role import UserClanRole


class SqlAlchemyPlatformAdminQueryPort(PlatformAdminQueryPort):
    """SQLAlchemy implementation of Platform Admin read persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_clans(self, cursor: str | None, limit: int) -> Page[ClanSummaryView]:
        query = select(Clan)
        query = paginate_query(query, Clan, cursor, limit)
        result = await self._session.execute(query)
        clans = list(result.scalars().all())

        page = build_page(clans, limit)
        meta = page["meta"]
        return Page(
            data=[
                ClanSummaryView(
                    id=c.id,
                    name=c.name,
                    slug=c.slug,
                    is_active=c.is_active,
                    created_at=c.created_at,
                )
                for c in page["data"]
            ],
            meta=PageMeta(cursor=meta["cursor"], has_more=meta["has_more"], limit=meta["limit"]),
        )

    async def get_clan_detail(self, clan_id: uuid.UUID) -> ClanDetailView:
        result = await self._session.execute(select(Clan).where(Clan.id == clan_id))
        clan = result.scalar_one_or_none()
        if not clan:
            raise NotFoundError("clan_not_found")

        total_members = (
            await self._session.scalar(
                select(func.count(func.distinct(Person.id)))
                .select_from(ClanMembership)
                .join(Person, Person.id == ClanMembership.person_id)
                .where(
                    ClanMembership.clan_id == clan_id,
                    Person.is_deleted.is_(False),
                )
            )
            or 0
        )
        total_users = (
            await self._session.scalar(
                select(func.count(func.distinct(UserClanRole.user_id))).where(
                    UserClanRole.clan_id == clan_id
                )
            )
            or 0
        )

        return ClanDetailView(
            id=clan.id,
            name=clan.name,
            slug=clan.slug,
            is_active=clan.is_active,
            description=clan.description,
            origin_place=clan.origin_place,
            created_at=clan.created_at,
            stats=ClanStatsView(
                total_members=total_members,
                total_users=total_users,
            ),
        )

    async def get_metrics(self) -> PlatformMetricsView:
        total_clans = select(func.count()).select_from(Clan).scalar_subquery()
        active_clans = (
            select(func.count()).select_from(Clan).where(Clan.is_active.is_(True)).scalar_subquery()
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

        return PlatformMetricsView(
            total_clans=row.total_clans or 0,
            active_clans=row.active_clans or 0,
            suspended_clans=(row.total_clans or 0) - (row.active_clans or 0),
            total_members=row.total_members or 0,
            total_users=row.total_users or 0,
        )

    async def get_audit_log(
        self,
        clan_id: uuid.UUID | None,
        action: str | None,
        cursor: str | None,
        limit: int,
    ) -> Page[AuditLogEntryView]:
        query = select(AuditLog)
        if clan_id:
            query = query.where(AuditLog.clan_id == clan_id)
        if action:
            query = query.where(AuditLog.action == action)

        query = paginate_query(query, AuditLog, cursor, limit)
        result = await self._session.execute(query)
        entries = list(result.scalars().all())

        page = build_page(entries, limit)
        meta = page["meta"]
        return Page(
            data=[
                AuditLogEntryView(
                    id=e.id,
                    clan_id=e.clan_id,
                    actor_id=e.actor_id,
                    actor_role=e.actor_role,
                    action=e.action,
                    resource_type=e.resource_type,
                    resource_id=e.resource_id,
                    created_at=e.created_at,
                )
                for e in page["data"]
            ],
            meta=PageMeta(cursor=meta["cursor"], has_more=meta["has_more"], limit=meta["limit"]),
        )
