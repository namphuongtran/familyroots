"""Platform admin use-case handlers.

Super-admin operations: clan management, metrics, audit log.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.application.shared.audit import emit_audit_event
from app.core.exceptions import NotFoundError
from app.domain.clan.repository import ClanRepository
from app.domain.platform_admin.query_port import (
    AuditLogEntryView,
    ClanSummaryView,
    PlatformAdminQueryPort,
)
from app.domain.shared.unit_of_work import UnitOfWork
from app.domain.shared.value_objects import ActorInfo


class PlatformAdminCommandHandler:
    """Handles platform admin write operations."""

    def __init__(self, repo: ClanRepository, uow: UnitOfWork) -> None:
        self._repo = repo
        self._uow = uow

    async def suspend_clan(self, *, clan_id: uuid.UUID, actor: ActorInfo) -> None:
        clan = await self._repo.get_clan(clan_id)
        if not clan:
            raise NotFoundError("clan_not_found")

        clan.is_active = False

        await emit_audit_event(
            self._uow,
            action="clan.suspend",
            resource_type="clan",
            resource_id=clan_id,
            actor=actor,
            clan_id=clan_id,
        )

    async def reactivate_clan(self, *, clan_id: uuid.UUID, actor: ActorInfo) -> None:
        clan = await self._repo.get_clan(clan_id)
        if not clan:
            raise NotFoundError("clan_not_found")

        clan.is_active = True

        await emit_audit_event(
            self._uow,
            action="clan.reactivate",
            resource_type="clan",
            resource_id=clan_id,
            actor=actor,
            clan_id=clan_id,
        )


class PlatformAdminQueryHandler:
    """Read-only handler for platform admin queries."""

    def __init__(self, query_port: PlatformAdminQueryPort) -> None:
        self._query_port = query_port

    async def list_clans(self, *, cursor: str | None, limit: int) -> dict[str, Any]:
        page = await self._query_port.list_clans(cursor, limit)
        return {
            "data": [_clan_summary(c) for c in page.data],
            "meta": {
                "cursor": page.meta.cursor,
                "has_more": page.meta.has_more,
                "limit": page.meta.limit,
            },
        }

    async def get_clan_detail(self, *, clan_id: uuid.UUID) -> dict[str, Any]:
        detail = await self._query_port.get_clan_detail(clan_id)
        return {
            "id": str(detail.id),
            "name": detail.name,
            "slug": detail.slug,
            "is_active": detail.is_active,
            "description": detail.description,
            "origin_place": detail.origin_place,
            "created_at": detail.created_at.isoformat() if detail.created_at else None,
            "stats": {
                "total_members": detail.stats.total_members,
                "total_users": detail.stats.total_users,
            },
        }

    async def get_metrics(self) -> dict[str, Any]:
        metrics = await self._query_port.get_metrics()
        return {
            "total_clans": metrics.total_clans,
            "active_clans": metrics.active_clans,
            "suspended_clans": metrics.suspended_clans,
            "total_members": metrics.total_members,
            "total_users": metrics.total_users,
        }

    async def get_audit_log(
        self,
        *,
        clan_id: uuid.UUID | None,
        action: str | None,
        cursor: str | None,
        limit: int,
    ) -> dict[str, Any]:
        page = await self._query_port.get_audit_log(clan_id, action, cursor, limit)
        return {
            "data": [_audit_entry(e) for e in page.data],
            "meta": {
                "cursor": page.meta.cursor,
                "has_more": page.meta.has_more,
                "limit": page.meta.limit,
            },
        }


def _clan_summary(c: ClanSummaryView) -> dict[str, Any]:
    """Serialize a clan-summary read model to the API wire shape."""
    return {
        "id": str(c.id),
        "name": c.name,
        "slug": c.slug,
        "is_active": c.is_active,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _audit_entry(e: AuditLogEntryView) -> dict[str, Any]:
    """Serialize an audit-log read model to the API wire shape."""
    return {
        "id": str(e.id),
        "clan_id": str(e.clan_id) if e.clan_id else None,
        "actor_id": str(e.actor_id),
        "actor_role": e.actor_role,
        "action": e.action,
        "resource_type": e.resource_type,
        "resource_id": str(e.resource_id) if e.resource_id else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
