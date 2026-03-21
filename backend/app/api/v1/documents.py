"""Documents API routes — thin controller delegating to Document handlers."""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.application.document.handlers import DocumentCommandHandler, DocumentQueryHandler
from app.core.permissions import ClanRole, RequireAdmin, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.value_objects import ActorInfo

router = APIRouter()


from app.infrastructure.dependencies import get_document_command_handler, get_document_query_handler


@router.post("", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: str = Form(...),
    person_id: uuid.UUID | None = Form(None),
    description: str | None = Form(None),
    taken_date: date | None = Form(None),
    taken_place: str | None = Form(None),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: DocumentCommandHandler = Depends(get_document_command_handler),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Upload a document/photo to storage and save metadata."""
    content = await file.read()
    result = await cmd_handler.upload(
        file_content=content,
        filename=file.filename,
        content_type=file.content_type,
        title=title,
        document_type=document_type,
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, "editor"),
        person_id=person_id,
        description=description,
        taken_date=taken_date,
        taken_place=taken_place,
    )
    return {"data": result.model_dump()}


@router.get("")
async def list_documents(
    person_id: uuid.UUID | None = Query(None),
    document_type: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: DocumentQueryHandler = Depends(get_document_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """List documents with optional filters, paginated."""
    items = await query_handler.list_documents(
        clan_id=clan_id,
        person_id=person_id,
        document_type=document_type,
        cursor=cursor,
        limit=limit,
    )
    return {"data": [item.model_dump() for item in items]}


@router.get("/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: DocumentQueryHandler = Depends(get_document_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get document metadata with a presigned download URL."""
    result = await query_handler.get(document_id=document_id, clan_id=clan_id)
    return {"data": result.model_dump()}


@router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: DocumentCommandHandler = Depends(get_document_command_handler),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Delete a document from storage and the database (admin only)."""
    await cmd_handler.delete(
        document_id=document_id,
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, "admin"),
    )
    return {"data": {"message": "Document deleted", "id": str(document_id)}}


@router.patch("/{document_id}/set-avatar")
async def set_document_as_avatar(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: DocumentCommandHandler = Depends(get_document_command_handler),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Set a photo document as the person's avatar."""
    await cmd_handler.set_avatar(document_id=document_id, clan_id=clan_id)
    return {"data": {"message": "Avatar set", "document_id": str(document_id)}}
