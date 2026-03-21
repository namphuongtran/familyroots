"""Platform admin API routes — thin controller delegating to PlatformAdmin handlers.

All routes in this module are protected by the ``get_super_admin`` dependency.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.platform_admin.handlers import (
    PlatformAdminCommandHandler,
    PlatformAdminQueryHandler,
)
from app.core.database import get_db
from app.core.security import get_super_admin
from app.domain.shared.value_objects import ActorInfo
from app.models.user_profile import UserProfile

router = APIRouter(prefix="/platform", tags=["Platform Admin"])


def _make_cmd_handler(db: AsyncSession) -> PlatformAdminCommandHandler:
    from app.infrastructure.event_dispatcher import create_event_dispatcher
    from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    return PlatformAdminCommandHandler(db, uow)


@router.get("/clans", dependencies=[Depends(get_super_admin)])
async def list_all_clans(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all clans on the platform."""
    handler = PlatformAdminQueryHandler(db)
    return await handler.list_clans(cursor=cursor, limit=limit)


@router.get("/clans/{clan_id}", dependencies=[Depends(get_super_admin)])
async def get_clan_detail(
    clan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get detailed clan info with aggregate stats."""
    handler = PlatformAdminQueryHandler(db)
    result = await handler.get_clan_detail(clan_id=clan_id)
    return {"data": result}


@router.post("/clans/{clan_id}/suspend")
async def suspend_clan(
    clan_id: uuid.UUID,
    profile: UserProfile = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Suspend a clan."""
    handler = _make_cmd_handler(db)
    actor = ActorInfo(user_id=profile.id, role=profile.platform_role or "super_admin")
    await handler.suspend_clan(clan_id=clan_id, actor=actor)
    return {"data": {"is_active": False, "clan_id": str(clan_id)}}


@router.post("/clans/{clan_id}/reactivate")
async def reactivate_clan(
    clan_id: uuid.UUID,
    profile: UserProfile = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reactivate a suspended clan."""
    handler = _make_cmd_handler(db)
    actor = ActorInfo(user_id=profile.id, role=profile.platform_role or "super_admin")
    await handler.reactivate_clan(clan_id=clan_id, actor=actor)
    return {"data": {"is_active": True, "clan_id": str(clan_id)}}


@router.get("/metrics", dependencies=[Depends(get_super_admin)])
async def platform_metrics(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Platform-wide usage metrics."""
    handler = PlatformAdminQueryHandler(db)
    result = await handler.get_metrics()
    return {"data": result}


@router.get("/audit-log", dependencies=[Depends(get_super_admin)])
async def audit_log(
    clan_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cross-clan audit log."""
    handler = PlatformAdminQueryHandler(db)
    return await handler.get_audit_log(
        clan_id=clan_id, action=action, cursor=cursor, limit=limit,
    )
