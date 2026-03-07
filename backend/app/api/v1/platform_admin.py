"""Platform admin API routes — super admin only.

All routes in this module are protected by the ``get_super_admin`` dependency
and require the caller to be the platform super admin.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.core.pagination import build_page, paginate_query
from app.core.security import get_super_admin
from app.models.audit_log import AuditLog
from app.models.clan import Clan
from app.models.member import Member
from app.models.user_clan_role import UserClanRole

router = APIRouter(prefix="/platform", tags=["Platform Admin"])


@router.get("/clans", dependencies=[Depends(get_super_admin)])
async def list_all_clans(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all clans on the platform with pagination."""
    query = select(Clan)
    query = paginate_query(query, Clan, cursor, limit)
    result = await db.execute(query)
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


@router.get("/clans/{clan_id}", dependencies=[Depends(get_super_admin)])
async def get_clan_detail(
    clan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get detailed clan info with aggregate stats."""
    result = await db.execute(select(Clan).where(Clan.id == clan_id))
    clan = result.scalar_one_or_none()
    if not clan:
        raise NotFoundError("clan_not_found")

    # Gather stats
    member_count = await db.execute(
        select(func.count())
        .select_from(Member)
        .where(Member.clan_id == clan_id, Member.is_deleted.is_(False))
    )
    user_count = await db.execute(
        select(func.count()).select_from(UserClanRole).where(UserClanRole.clan_id == clan_id)
    )

    return {
        "data": {
            "id": str(clan.id),
            "name": clan.name,
            "slug": clan.slug,
            "is_active": clan.is_active,
            "description": clan.description,
            "origin_place": clan.origin_place,
            "created_at": clan.created_at.isoformat() if clan.created_at else None,
            "stats": {
                "total_members": member_count.scalar() or 0,
                "total_users": user_count.scalar() or 0,
            },
        }
    }


@router.post("/clans/{clan_id}/suspend", dependencies=[Depends(get_super_admin)])
async def suspend_clan(
    clan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Suspend a clan — sets status to 'suspended'."""
    result = await db.execute(select(Clan).where(Clan.id == clan_id))
    clan = result.scalar_one_or_none()
    if not clan:
        raise NotFoundError("clan_not_found")

    clan.is_active = False
    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            actor_role="super_admin",
            action="clan.suspend",
            resource_type="clan",
            resource_id=clan_id,
        )
    )
    await db.commit()
    return {"data": {"is_active": False, "clan_id": str(clan_id)}}


@router.post("/clans/{clan_id}/reactivate", dependencies=[Depends(get_super_admin)])
async def reactivate_clan(
    clan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reactivate a suspended clan — sets status to 'active'."""
    result = await db.execute(select(Clan).where(Clan.id == clan_id))
    clan = result.scalar_one_or_none()
    if not clan:
        raise NotFoundError("clan_not_found")

    clan.is_active = True
    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            actor_role="super_admin",
            action="clan.reactivate",
            resource_type="clan",
            resource_id=clan_id,
        )
    )
    await db.commit()
    return {"data": {"is_active": True, "clan_id": str(clan_id)}}


@router.get("/metrics", dependencies=[Depends(get_super_admin)])
async def platform_metrics(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Platform-wide usage metrics."""
    total_clans = (await db.execute(select(func.count()).select_from(Clan))).scalar() or 0
    active_clans = (
        await db.execute(select(func.count()).select_from(Clan).where(Clan.is_active.is_(True)))
    ).scalar() or 0
    total_members = (
        await db.execute(
            select(func.count()).select_from(Member).where(Member.is_deleted.is_(False))
        )
    ).scalar() or 0
    total_users = (await db.execute(select(func.count()).select_from(UserClanRole))).scalar() or 0

    return {
        "data": {
            "total_clans": total_clans,
            "active_clans": active_clans,
            "suspended_clans": total_clans - active_clans,
            "total_members": total_members,
            "total_users": total_users,
        }
    }


@router.get("/audit-log", dependencies=[Depends(get_super_admin)])
async def audit_log(
    clan_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cross-clan audit log with optional filters."""
    query = select(AuditLog)
    if clan_id:
        query = query.where(AuditLog.clan_id == clan_id)
    if action:
        query = query.where(AuditLog.action == action)

    query = paginate_query(query, AuditLog, cursor, limit)
    result = await db.execute(query)
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
