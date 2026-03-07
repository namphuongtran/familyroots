"""Clan management API routes — clan info, user approval, role management."""

import uuid
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.pagination import build_page, paginate_query
from app.core.permissions import ClanRole, RequireAdmin, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.models.audit_log import AuditLog
from app.models.clan import Clan
from app.models.user_clan_role import UserClanRole
from app.schemas.clan import ClanResponse, ClanUpdateRequest
from app.services.translator import t

router = APIRouter()


@router.get("/me")
async def get_own_clan(
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get the current user's active clan info."""
    clan = await db.get(Clan, clan_id)
    if not clan:
        raise NotFoundError("clan_not_found")
    return {"data": ClanResponse.model_validate(clan).model_dump()}


@router.patch("/me")
async def update_own_clan(
    body: ClanUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Update current clan info (admin only)."""
    clan = await db.get(Clan, clan_id)
    if not clan:
        raise NotFoundError("clan_not_found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(clan, field, value)

    db.add(AuditLog(
        clan_id=clan_id,
        actor_id=uuid.UUID(current_user["sub"]),
        actor_role="admin",
        action="clan.update",
        resource_type="clan",
        resource_id=clan_id,
        new_value=update_data,
    ))
    await db.commit()
    return {"data": ClanResponse.model_validate(clan).model_dump()}


@router.get("/me/users")
async def list_clan_users(
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
    cursor: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List approved users in the current clan (paginated)."""
    query = select(UserClanRole).where(
        UserClanRole.clan_id == clan_id, UserClanRole.is_approved.is_(True)
    )
    query = paginate_query(query, UserClanRole, cursor, min(limit, 100))
    result = await db.execute(query)
    items = list(result.scalars().all())
    page = build_page(items, min(limit, 100))
    page["data"] = [
        {
            "id": str(u.id),
            "user_id": str(u.user_id),
            "role": u.role,
            "member_id": str(u.member_id) if u.member_id else None,
            "created_at": u.created_at.isoformat(),
        }
        for u in page["data"]
    ]
    return page


@router.get("/me/users/pending")
async def list_pending_users(
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
    cursor: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List users pending approval (admin only)."""
    query = select(UserClanRole).where(
        UserClanRole.clan_id == clan_id, UserClanRole.is_approved.is_(False)
    )
    query = paginate_query(query, UserClanRole, cursor, min(limit, 100))
    result = await db.execute(query)
    items = list(result.scalars().all())
    page = build_page(items, min(limit, 100))
    page["data"] = [
        {
            "id": str(u.id),
            "user_id": str(u.user_id),
            "role": u.role,
            "created_at": u.created_at.isoformat(),
        }
        for u in page["data"]
    ]
    return page


@router.post("/me/users/{user_id}/approve")
async def approve_user(
    user_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Approve a pending user (admin only)."""
    result = await db.execute(
        select(UserClanRole).where(
            UserClanRole.clan_id == clan_id, UserClanRole.user_id == user_id
        )
    )
    ucr = result.scalar_one_or_none()
    if not ucr:
        raise NotFoundError("user_not_found")
    if ucr.is_approved:
        raise ConflictError("user.already_approved")

    ucr.is_approved = True
    ucr.approved_by = uuid.UUID(current_user["sub"])
    from datetime import datetime
    ucr.approved_at = datetime.now(UTC)

    db.add(AuditLog(
        clan_id=clan_id,
        actor_id=uuid.UUID(current_user["sub"]),
        actor_role="admin",
        action="user.approve",
        resource_type="user_clan_role",
        resource_id=ucr.id,
    ))
    await db.commit()
    return {"data": {"message": t("user.approved"), "user_id": str(user_id)}}


@router.post("/me/users/{user_id}/reject")
async def reject_user(
    user_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Reject a pending user (admin only). Deletes the membership row."""
    result = await db.execute(
        select(UserClanRole).where(
            UserClanRole.clan_id == clan_id,
            UserClanRole.user_id == user_id,
            UserClanRole.is_approved.is_(False),
        )
    )
    ucr = result.scalar_one_or_none()
    if not ucr:
        raise NotFoundError("user_not_found")

    await db.delete(ucr)
    db.add(AuditLog(
        clan_id=clan_id,
        actor_id=uuid.UUID(current_user["sub"]),
        actor_role="admin",
        action="user.reject",
        resource_type="user_clan_role",
        resource_id=ucr.id,
    ))
    await db.commit()
    return {"data": {"message": t("user.rejected"), "user_id": str(user_id)}}


@router.patch("/me/users/{user_id}/role")
async def change_user_role(
    user_id: uuid.UUID,
    role: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Change a user's clan role (admin only)."""
    if role not in ("admin", "editor", "viewer"):
        raise ValidationError(
            "validation",
            {"field": "role", "allowed": ["admin", "editor", "viewer"]},
        )

    actor_id = uuid.UUID(current_user["sub"])

    result = await db.execute(
        select(UserClanRole).where(
            UserClanRole.clan_id == clan_id, UserClanRole.user_id == user_id
        )
    )
    ucr = result.scalar_one_or_none()
    if not ucr:
        raise NotFoundError("user_not_found")

    # Prevent demoting yourself if you're the only admin
    if user_id == actor_id and role != "admin":
        admin_count = await db.execute(
            select(func.count()).where(
                UserClanRole.clan_id == clan_id,
                UserClanRole.role == "admin",
                UserClanRole.is_approved.is_(True),
            )
        )
        if (admin_count.scalar() or 0) <= 1:
            raise ForbiddenError("clan.last_admin_cannot_demote")

    old_role = ucr.role
    ucr.role = role

    db.add(AuditLog(
        clan_id=clan_id,
        actor_id=actor_id,
        actor_role="admin",
        action="user.change_role",
        resource_type="user_clan_role",
        resource_id=ucr.id,
        old_value={"role": old_role},
        new_value={"role": role},
    ))
    await db.commit()
    return {"data": {"message": t("user.role_changed"), "user_id": str(user_id), "role": role}}


@router.delete("/me/users/{user_id}")
async def remove_user(
    user_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Remove a user from the clan (admin only)."""
    actor_id = uuid.UUID(current_user["sub"])

    if user_id == actor_id:
        raise ForbiddenError("clan.cannot_remove_self")

    result = await db.execute(
        select(UserClanRole).where(
            UserClanRole.clan_id == clan_id, UserClanRole.user_id == user_id
        )
    )
    ucr = result.scalar_one_or_none()
    if not ucr:
        raise NotFoundError("user_not_found")

    await db.delete(ucr)
    db.add(AuditLog(
        clan_id=clan_id,
        actor_id=actor_id,
        actor_role="admin",
        action="user.remove",
        resource_type="user_clan_role",
        resource_id=ucr.id,
    ))
    await db.commit()
    return {"data": {"message": t("user.removed"), "user_id": str(user_id)}}
