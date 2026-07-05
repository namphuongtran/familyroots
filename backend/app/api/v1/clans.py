"""Clan management API routes — thin controller delegating to use-case handlers.

Clan info, user listing, approval, rejection, role management,
and user removal — all with automatic audit logging via domain events.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.application.clan.commands import (
    ApproveUser,
    ChangeUserRole,
    RejectUser,
    RemoveUser,
    UpdateClan,
)
from app.application.clan.handlers import ClanCommandHandler, ClanQueryHandler
from app.core.permissions import ClanRole, RequireAdmin, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.exceptions import EntityNotFoundError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.dependencies import get_clan_command_handler, get_clan_query_handler
from app.schemas.clan import ClanResponse, ClanStats, ClanUpdateRequest
from app.services.translator import t

router = APIRouter()


@router.get("/me")
async def get_own_clan(
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: ClanQueryHandler = Depends(get_clan_query_handler),
    _role: ClanRole = RequireViewer,
    include: str | None = Query(None),
) -> dict[str, Any]:
    """Get the current user's active clan info."""
    clan = await query_handler.get_clan(clan_id)
    if not clan:
        raise EntityNotFoundError("clan_not_found")

    data = ClanResponse.model_validate(clan).model_dump()
    includes = {item.strip() for item in include.split(",")} if include else set()
    if "stats" in includes:
        stats = await query_handler.get_clan_stats(clan_id)
        data["stats"] = ClanStats.model_validate(stats).model_dump()

    return {"data": data}


@router.patch("/me")
async def update_own_clan(
    body: ClanUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ClanCommandHandler = Depends(get_clan_command_handler),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Update current clan info (admin only)."""
    clan = await handler.update_clan(
        UpdateClan(
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, "admin"),
            changes=body.model_dump(exclude_unset=True),
        )
    )
    return {"data": ClanResponse.model_validate(clan).model_dump()}


@router.get("/me/users")
async def list_clan_users(
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: ClanQueryHandler = Depends(get_clan_query_handler),
    _role: ClanRole = RequireViewer,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """List approved users in the current clan (paginated)."""
    page = await query_handler.list_users(clan_id, approved=True, cursor=cursor, limit=limit)
    page["data"] = [
        {
            "id": str(u.id),
            "user_id": str(u.user_id),
            "role": u.role,
            "person_id": str(u.person_id) if u.person_id else None,
            "created_at": u.created_at.isoformat(),
        }
        for u in page["data"]
    ]
    return page


@router.get("/me/users/pending")
async def list_pending_users(
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: ClanQueryHandler = Depends(get_clan_query_handler),
    _role: ClanRole = RequireAdmin,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """List users pending approval (admin only)."""
    page = await query_handler.list_users(clan_id, approved=False, cursor=cursor, limit=limit)
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
    handler: ClanCommandHandler = Depends(get_clan_command_handler),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Approve a pending user (admin only)."""
    await handler.approve_user(
        ApproveUser(
            clan_id=clan_id,
            target_user_id=user_id,
            actor=ActorInfo.from_jwt(current_user, "admin"),
        )
    )
    return {"data": {"message": t("user.approved"), "user_id": str(user_id)}}


@router.post("/me/users/{user_id}/reject")
async def reject_user(
    user_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ClanCommandHandler = Depends(get_clan_command_handler),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Reject a pending user (admin only)."""
    await handler.reject_user(
        RejectUser(
            clan_id=clan_id,
            target_user_id=user_id,
            actor=ActorInfo.from_jwt(current_user, "admin"),
        )
    )
    return {"data": {"message": t("user.rejected"), "user_id": str(user_id)}}


@router.patch("/me/users/{user_id}/role")
async def change_user_role(
    user_id: uuid.UUID,
    role: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ClanCommandHandler = Depends(get_clan_command_handler),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Change a user's clan role (admin only)."""
    await handler.change_role(
        ChangeUserRole(
            clan_id=clan_id,
            target_user_id=user_id,
            new_role=role,
            actor=ActorInfo.from_jwt(current_user, "admin"),
        )
    )
    return {"data": {"message": t("user.role_changed"), "user_id": str(user_id), "role": role}}


@router.delete("/me/users/{user_id}")
async def remove_user(
    user_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ClanCommandHandler = Depends(get_clan_command_handler),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Remove a user from the clan (admin only)."""
    await handler.remove_user(
        RemoveUser(
            clan_id=clan_id,
            target_user_id=user_id,
            actor=ActorInfo.from_jwt(current_user, "admin"),
        )
    )
    return {"data": {"message": t("user.removed"), "user_id": str(user_id)}}
