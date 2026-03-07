"""Me API routes — current user's clan memberships and clan switcher."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user

router = APIRouter()


@router.get("/clans")
async def list_my_clans(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all clans the authenticated user belongs to.

    Used by the clan switcher UI (similar to Slack's workspace switcher).
    Returns all approved memberships with clan details and role.
    """
    user_id = current_user["sub"]

    # TODO: implement in Prompt 2 — replace with ORM join query
    result = await db.execute(
        text(
            "SELECT ucr.clan_id, c.name AS clan_name, c.slug AS clan_slug, "
            "ucr.role, ucr.joined_at "
            "FROM user_clan_roles ucr "
            "JOIN clans c ON c.id = ucr.clan_id "
            "WHERE ucr.user_id = :user_id AND ucr.is_approved = true "
            "ORDER BY ucr.joined_at"
        ),
        {"user_id": user_id},
    )
    rows = result.fetchall()

    return {
        "clans": [
            {
                "clan_id": str(row.clan_id),
                "clan_name": row.clan_name,
                "clan_slug": row.clan_slug,
                "role": row.role,
                "joined_at": row.joined_at.isoformat() if row.joined_at else None,
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.post("/clans/{clan_id}/select")
async def select_clan(
    clan_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Select a clan as the active context.

    Validates that the user has an approved membership in the target clan.
    The client should persist the returned ``clan_id`` and send it as the
    ``X-Current-Clan-Id`` header on all subsequent clan-scoped API calls.
    """
    user_id = current_user["sub"]

    # TODO: implement in Prompt 2 — replace with ORM query
    result = await db.execute(
        text(
            "SELECT ucr.clan_id, c.name AS clan_name, c.slug AS clan_slug, "
            "ucr.role "
            "FROM user_clan_roles ucr "
            "JOIN clans c ON c.id = ucr.clan_id "
            "WHERE ucr.user_id = :user_id AND ucr.clan_id = :clan_id "
            "AND ucr.is_approved = true"
        ),
        {"user_id": user_id, "clan_id": str(clan_id)},
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(
            status_code=403,
            detail="You do not have approved membership in this clan",
        )

    return {
        "clan_id": str(row.clan_id),
        "clan_name": row.clan_name,
        "clan_slug": row.clan_slug,
        "role": row.role,
        "message": (
            "Clan selected. Set X-Current-Clan-Id header"
            " to this clan_id on subsequent requests."
        ),
    }
