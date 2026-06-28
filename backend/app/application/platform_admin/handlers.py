"""Platform admin use-case handlers.

Super-admin operations: clan management, metrics, audit log.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.application.shared.audit import emit_audit_event
from app.core.exceptions import NotFoundError
from app.domain.clan.repository import ClanRepository
from app.domain.platform_admin.query_port import PlatformAdminQueryPort
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
        return await self._query_port.list_clans(cursor, limit)

    async def get_clan_detail(self, *, clan_id: uuid.UUID) -> dict[str, Any]:
        return await self._query_port.get_clan_detail(clan_id)

    async def get_metrics(self) -> dict[str, Any]:
        return await self._query_port.get_metrics()

    async def get_audit_log(
        self,
        *,
        clan_id: uuid.UUID | None,
        action: str | None,
        cursor: str | None,
        limit: int,
    ) -> dict[str, Any]:
        return await self._query_port.get_audit_log(clan_id, action, cursor, limit)
