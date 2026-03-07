"""JWT validation via Supabase JWKS, auth dependencies, and super admin guard."""

import time
import uuid
from typing import Any

import httpx
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

security = HTTPBearer()

_jwks_cache: dict[str, Any] | None = None
_jwks_cache_time: float = 0.0
_JWKS_TTL: float = 3600.0  # 1 hour


async def get_supabase_jwks() -> dict[str, Any]:
    """Fetch Supabase public JWKS with in-memory caching (1-hour TTL)."""
    global _jwks_cache, _jwks_cache_time
    now = time.monotonic()
    if _jwks_cache is not None and (now - _jwks_cache_time) < _JWKS_TTL:
        return _jwks_cache

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json")
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_cache_time = now
        return _jwks_cache


async def verify_supabase_token(token: str) -> dict[str, Any]:
    """Validate a Supabase-issued JWT. Returns the decoded payload."""
    try:
        jwks = await get_supabase_jwks()
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience="authenticated",
        )
        return payload
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    """FastAPI dependency — extract and validate JWT from Authorization header."""
    return await verify_supabase_token(credentials.credentials)


async def get_super_admin(
    current_user: dict[str, Any] = Depends(get_current_user),
    # TODO: implement in Prompt 2 — inject AsyncSession via get_db dependency
    # db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Dependency that allows access only to the platform super admin.

    Checks ``public.platform_users`` table for an active super_admin row
    matching the current user's JWT ``sub`` claim.
    """
    # TODO: implement in Prompt 2 — query PlatformUser model from DB
    # user_id = current_user["sub"]
    # result = await db.execute(
    #     select(PlatformUser).where(
    #         PlatformUser.id == user_id,
    #         PlatformUser.role == "super_admin",
    #         PlatformUser.is_active == True,
    #     )
    # )
    # platform_user = result.scalar_one_or_none()
    # if not platform_user:
    #     raise HTTPException(status_code=403, detail="Super admin access required")

    # Temporary: check JWT metadata until DB model is wired in Prompt 2
    user_metadata = current_user.get("user_metadata", {})
    if user_metadata.get("platform_role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin access required")

    return current_user


async def get_current_clan_id(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    x_current_clan_id: str | None = Header(default=None),
) -> uuid.UUID:
    """Resolve the active clan_id for the authenticated user.

    Implements a Slack-style clan switcher:
    - Client sends ``X-Current-Clan-Id`` header to select active clan.
    - If user belongs to exactly one clan and no header is sent,
      the single clan is auto-selected (zero-friction UX).
    - If user belongs to multiple clans and no header is sent,
      returns 400 asking the client to specify one.
    - If header is sent but user doesn't belong to that clan, returns 403.

    Used as a FastAPI dependency on all clan-scoped endpoints.
    """
    # TODO: implement in Prompt 2 — replace with real UserClanRole model import
    # from app.models.user_clan_role import UserClanRole
    #
    # For now, use raw SQL text query as the model is not yet defined:
    from sqlalchemy import text

    user_id = current_user["sub"]

    # Fetch all approved clan memberships for this user
    result = await db.execute(
        text("SELECT clan_id FROM user_clan_roles WHERE user_id = :user_id AND is_approved = true"),
        {"user_id": user_id},
    )
    approved_clan_ids: list[uuid.UUID] = [uuid.UUID(str(row[0])) for row in result.fetchall()]

    if not approved_clan_ids:
        raise HTTPException(status_code=403, detail="No approved clan membership")

    # If client specifies a clan via header, validate membership
    if x_current_clan_id is not None:
        try:
            requested_clan_id = uuid.UUID(x_current_clan_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid X-Current-Clan-Id format") from exc

        if requested_clan_id not in approved_clan_ids:
            raise HTTPException(
                status_code=403,
                detail="You do not have approved membership in this clan",
            )
        return requested_clan_id

    # No header: auto-select if exactly one clan
    if len(approved_clan_ids) == 1:
        return approved_clan_ids[0]

    # Multiple clans, no header — client must specify
    raise HTTPException(
        status_code=400,
        detail=(
            "You belong to multiple clans. "
            "Set X-Current-Clan-Id header to select the active clan. "
            "Use GET /api/v1/me/clans to list your clans."
        ),
    )
