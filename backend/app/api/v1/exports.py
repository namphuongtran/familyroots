"""Clan export API route — thin controller delegating to ExportQueryHandler.

Envelope-EXEMPT: unlike every other 2xx endpoint, this returns the raw archive
bytes as an attachment, not `{"data": ...}` — the response body IS the file
the clan downloads.
"""

import uuid
from typing import Any

from fastapi import Depends, Query, Response
from fastapi.routing import APIRouter

from app.application.export.handlers import ExportQueryHandler
from app.core.permissions import ClanRole, RequireAdmin
from app.core.security import get_current_clan_id, get_current_user
from app.infrastructure.dependencies import get_export_query_handler

router = APIRouter()


@router.get("/clan")
async def export_clan(
    # `export_format` (not `format`) to avoid shadowing the builtin (ruff A002);
    # `alias="format"` keeps the wire contract `?format=json|gedcom` unchanged.
    export_format: str = Query("json", alias="format", pattern="^(json|gedcom)$"),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: ExportQueryHandler = Depends(get_export_query_handler),
    role: ClanRole = RequireAdmin,
) -> Response:
    """Download the full clan archive ("bản sao ngàn đời") — admin only."""
    filename, media_type, body = await query_handler.export_clan(clan_id, export_format)
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
