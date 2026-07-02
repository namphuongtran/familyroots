"""JWT validation via Supabase JWKS, auth dependencies, and super admin guard."""

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AppError, AuthenticationError, ForbiddenError
from app.models.user_profile import UserProfile

# auto_error=False so a MISSING/malformed Authorization header raises our own
# AuthenticationError (401) instead of FastAPI's bare HTTPException(403) — a present
# token that is invalid also yields 401, so "no/!bad credentials" is consistently 401.
security = HTTPBearer(auto_error=False)

# Thread-safe JWKS cache using asyncio.Lock
_jwks_cache: dict[str, Any] | None = None
_jwks_cache_time: float = 0.0
_jwks_lock: asyncio.Lock | None = None
_JWKS_TTL: float = 3600.0  # 1 hour


def _get_jwks_lock() -> asyncio.Lock:
    """Lazily create a Lock bound to the current event loop."""
    global _jwks_lock
    if _jwks_lock is None:
        _jwks_lock = asyncio.Lock()
    return _jwks_lock


async def get_supabase_jwks() -> dict[str, Any]:
    """Fetch Supabase public JWKS with thread-safe in-memory caching (1-hour TTL)."""
    global _jwks_cache, _jwks_cache_time

    # Fast path: check without lock
    now = time.monotonic()
    if _jwks_cache is not None and (now - _jwks_cache_time) < _JWKS_TTL:
        return _jwks_cache

    # Slow path: acquire lock, double-check, then fetch
    async with _get_jwks_lock():
        now = time.monotonic()
        if _jwks_cache is not None and (now - _jwks_cache_time) < _JWKS_TTL:
            return _jwks_cache

        async with httpx.AsyncClient() as client:
            url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
            resp = await client.get(url)
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
            issuer=f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        )
        return payload
    except JWTError as exc:
        raise AuthenticationError("invalid_token") from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any]:
    """FastAPI dependency — extract and validate JWT from Authorization header."""
    if credentials is None:
        raise AuthenticationError("missing_token")
    return await verify_supabase_token(credentials.credentials)


# Throttle last_login_at updates: skip if last update was less than 5 min ago.
_LOGIN_UPDATE_INTERVAL = 300  # seconds


async def ensure_user_profile(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    """Lazy-create or refresh the local UserProfile on every authenticated request.

    On first login the row is created from JWT claims.  On subsequent
    requests ``last_login_at`` is refreshed (throttled to once per 5 min).
    """
    user_id = uuid.UUID(current_user["sub"])

    result = await db.execute(select(UserProfile).where(UserProfile.id == user_id))
    profile = result.scalar_one_or_none()

    if profile is None:
        email: str = current_user.get("email", "")
        user_metadata: dict[str, Any] = current_user.get("user_metadata", {})
        display_name = user_metadata.get("full_name") or email.split("@")[0]

        profile = UserProfile(
            id=user_id,
            email=email,
            display_name=display_name,
            last_login_at=datetime.now(UTC),
        )
        db.add(profile)
        await db.flush()
    else:
        # Throttle: only update last_login_at if stale
        now = datetime.now(UTC)
        if (
            profile.last_login_at is None
            or (now - profile.last_login_at).total_seconds() > _LOGIN_UPDATE_INTERVAL
        ):
            profile.last_login_at = now
            await db.flush()

    return profile


async def get_super_admin(
    profile: UserProfile = Depends(ensure_user_profile),
) -> UserProfile:
    """Dependency that allows access only to the platform super admin.

    Queries ``user_profiles.platform_role`` for an active super_admin.
    """
    if profile.platform_role != "super_admin" or not profile.is_active:
        raise ForbiddenError("super_admin_required")
    return profile


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
    from app.models.user_clan_role import UserClanRole

    user_id = uuid.UUID(current_user["sub"])

    # Fetch all approved clan memberships for this user
    result = await db.execute(
        select(UserClanRole.clan_id).where(
            UserClanRole.user_id == user_id,
            UserClanRole.is_approved.is_(True),
        )
    )
    approved_clan_ids: list[uuid.UUID] = list(result.scalars().all())

    if not approved_clan_ids:
        raise ForbiddenError("no_approved_clan_membership")

    # Resolve the active clan from the header (validating membership) or auto-select.
    if x_current_clan_id is not None:
        try:
            resolved_clan_id = uuid.UUID(x_current_clan_id)
        except ValueError as exc:
            raise AppError(400, "invalid_clan_id_format") from exc

        if resolved_clan_id not in approved_clan_ids:
            raise ForbiddenError("clan_membership_required")
    elif len(approved_clan_ids) == 1:
        # No header: auto-select if exactly one clan.
        resolved_clan_id = approved_clan_ids[0]
    else:
        # Multiple clans, no header — client must specify via X-Current-Clan-Id.
        raise AppError(400, "multiple_clans_no_selection")

    # A suspended clan is off-limits to all its members, not just admins: reject
    # every clan-scoped request once the platform has deactivated the clan.
    from app.models.clan import Clan

    is_active = await db.scalar(select(Clan.is_active).where(Clan.id == resolved_clan_id))
    if not is_active:
        raise ForbiddenError("clan_suspended")

    return resolved_clan_id
