"""Platform admin API routes — thin controller delegating to PlatformAdmin handlers.

All routes in this module are protected by the ``get_super_admin`` dependency.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.application.platform_admin.handlers import (
    PlatformAdminCommandHandler,
    PlatformAdminQueryHandler,
)
from app.core.security import get_super_admin
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.dependencies import (
    get_platform_admin_command_handler,
    get_platform_admin_query_handler,
)
from app.models.user_profile import UserProfile

router = APIRouter(prefix="/platform", tags=["Platform Admin"])


@router.get("/clans", dependencies=[Depends(get_super_admin)])
async def list_all_clans(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    handler: PlatformAdminQueryHandler = Depends(get_platform_admin_query_handler),
) -> dict[str, Any]:
    """List all clans on the platform."""
    return await handler.list_clans(cursor=cursor, limit=limit)


@router.get("/clans/{clan_id}", dependencies=[Depends(get_super_admin)])
async def get_clan_detail(
    clan_id: uuid.UUID,
    handler: PlatformAdminQueryHandler = Depends(get_platform_admin_query_handler),
) -> dict[str, Any]:
    """Get detailed clan info with aggregate stats."""
    result = await handler.get_clan_detail(clan_id=clan_id)
    return {"data": result}


@router.post("/clans/{clan_id}/suspend")
async def suspend_clan(
    clan_id: uuid.UUID,
    profile: UserProfile = Depends(get_super_admin),
    handler: PlatformAdminCommandHandler = Depends(get_platform_admin_command_handler),
) -> dict[str, Any]:
    """Suspend a clan."""
    actor = ActorInfo(user_id=profile.id, role=profile.platform_role or "super_admin")
    await handler.suspend_clan(clan_id=clan_id, actor=actor)
    return {"data": {"is_active": False, "clan_id": str(clan_id)}}


@router.post("/clans/{clan_id}/reactivate")
async def reactivate_clan(
    clan_id: uuid.UUID,
    profile: UserProfile = Depends(get_super_admin),
    handler: PlatformAdminCommandHandler = Depends(get_platform_admin_command_handler),
) -> dict[str, Any]:
    """Reactivate a suspended clan."""
    actor = ActorInfo(user_id=profile.id, role=profile.platform_role or "super_admin")
    await handler.reactivate_clan(clan_id=clan_id, actor=actor)
    return {"data": {"is_active": True, "clan_id": str(clan_id)}}


@router.get("/metrics", dependencies=[Depends(get_super_admin)])
async def platform_metrics(
    handler: PlatformAdminQueryHandler = Depends(get_platform_admin_query_handler),
) -> dict[str, Any]:
    """Platform-wide usage metrics."""
    result = await handler.get_metrics()
    return {"data": result}


@router.get("/audit-log", dependencies=[Depends(get_super_admin)])
async def audit_log(
    clan_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    handler: PlatformAdminQueryHandler = Depends(get_platform_admin_query_handler),
) -> dict[str, Any]:
    """Cross-clan audit log."""
    return await handler.get_audit_log(
        clan_id=clan_id, action=action, cursor=cursor, limit=limit,
    )
