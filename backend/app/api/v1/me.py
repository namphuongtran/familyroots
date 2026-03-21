"""Me API routes — thin controller delegating to Me handler."""

import uuid
from typing import Any

from app.application.me.handlers import MeQueryHandler
from app.core.security import get_current_user
from app.infrastructure.dependencies import get_me_query_handler

router = APIRouter()


@router.get("/clans")
async def list_my_clans(
    current_user: dict[str, Any] = Depends(get_current_user),
    handler: MeQueryHandler = Depends(get_me_query_handler),
) -> dict[str, Any]:
    """List all clans the authenticated user belongs to."""
    return await handler.list_clans(user_id=current_user["sub"])


@router.post("/clans/{clan_id}/select")
async def select_clan(
    clan_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    handler: MeQueryHandler = Depends(get_me_query_handler),
) -> dict[str, Any]:
    """Select a clan as the active context."""
    return await handler.select_clan(user_id=current_user["sub"], clan_id=clan_id)
