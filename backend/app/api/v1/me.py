"""Me API routes — thin controller delegating to Me handler."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.me.handlers import MeQueryHandler
from app.core.database import get_db
from app.core.security import get_current_user

router = APIRouter()


@router.get("/clans")
async def list_my_clans(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all clans the authenticated user belongs to."""
    handler = MeQueryHandler(db)
    return await handler.list_clans(user_id=current_user["sub"])


@router.post("/clans/{clan_id}/select")
async def select_clan(
    clan_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Select a clan as the active context."""
    handler = MeQueryHandler(db)
    return await handler.select_clan(user_id=current_user["sub"], clan_id=clan_id)
