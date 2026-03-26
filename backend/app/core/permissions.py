"""RBAC permission dependencies for FastAPI endpoints."""

import uuid
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ensure_user_profile, get_current_clan_id, get_current_user
from app.schemas.auth import UserProfile


class ClanRole(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


# Role hierarchy: higher index = more permissions
ROLE_HIERARCHY = [ClanRole.VIEWER, ClanRole.EDITOR, ClanRole.ADMIN]


def require_role(minimum_role: ClanRole) -> Callable[..., Any]:
    """FastAPI dependency factory that enforces a minimum clan role.

    Queries the user's role for the *active clan* (resolved by
    ``get_current_clan_id``). A user may belong to multiple clans
    with different roles — filtering by both user_id and clan_id
    ensures we check the correct membership.

    Usage::

        @router.post("/persons", dependencies=[Depends(require_role(ClanRole.EDITOR))])
    """

    async def _check(
        current_user: dict[str, Any] = Depends(get_current_user),
        clan_id: uuid.UUID = Depends(get_current_clan_id),
        db: AsyncSession = Depends(get_db),
    ) -> ClanRole:
        from app.models.user_clan_role import UserClanRole

        user_id = current_user["sub"]
        result = await db.execute(
            select(UserClanRole.role, UserClanRole.is_approved).where(
                UserClanRole.user_id == user_id,
                UserClanRole.clan_id == clan_id,
            )
        )
        row = result.first()

        if not row or not row.is_approved:
            raise HTTPException(status_code=403, detail="No approved clan membership")

        try:
            user_role = ClanRole(row.role)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Invalid role assignment") from exc

        if ROLE_HIERARCHY.index(user_role) < ROLE_HIERARCHY.index(minimum_role):
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        return user_role

    return _check


class RequireClanRole:
    """FastAPI dependency that checks if the user has one of the allowed roles.

    Unlike ``require_role()`` which uses hierarchy (minimum role),
    this checks explicit membership in a set of allowed roles.

    Usage::

        user: UserProfile = Depends(RequireClanRole(["admin", "editor"]))
    """

    def __init__(self, allowed_roles: list[str]) -> None:
        self._allowed_roles = {ClanRole(r) for r in allowed_roles}

    async def __call__(
        self,
        profile: UserProfile = Depends(ensure_user_profile),
        clan_id: uuid.UUID = Depends(get_current_clan_id),
        db: AsyncSession = Depends(get_db),
    ) -> UserProfile:
        from app.models.user_clan_role import UserClanRole

        result = await db.execute(
            select(UserClanRole.role, UserClanRole.is_approved).where(
                UserClanRole.user_id == profile.id,
                UserClanRole.clan_id == clan_id,
            )
        )
        row = result.first()

        if not row or not row.is_approved:
            raise HTTPException(status_code=403, detail="No approved clan membership")

        try:
            user_role = ClanRole(row.role)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Invalid role assignment") from exc

        if user_role not in self._allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        return profile


# Convenience dependencies (hierarchy-based)
RequireViewer = Depends(require_role(ClanRole.VIEWER))
RequireEditor = Depends(require_role(ClanRole.EDITOR))
RequireAdmin = Depends(require_role(ClanRole.ADMIN))

# Alias for active user check (same as ensure_user_profile)
require_active_user = ensure_user_profile
