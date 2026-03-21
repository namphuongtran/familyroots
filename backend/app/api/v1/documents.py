"""Documents API routes — thin controller delegating to Document handlers."""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.document.handlers import DocumentCommandHandler, DocumentQueryHandler
from app.core.database import get_db
from app.core.permissions import ClanRole, RequireAdmin, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.value_objects import ActorInfo

router = APIRouter()


def _make_handlers(
    db: AsyncSession,
) -> tuple[DocumentCommandHandler, DocumentQueryHandler]:
    from app.infrastructure.event_dispatcher import create_event_dispatcher
    from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
    from app.infrastructure.storage.supabase_adapter import SupabaseStorageAdapter
    from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

    repo = SqlAlchemyDocumentRepository(db)
    storage = SupabaseStorageAdapter()
    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    return (
        DocumentCommandHandler(repo, storage, uow),
        DocumentQueryHandler(repo, storage),
    )


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
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Upload a document/photo to storage and save metadata."""
    cmd_handler, _ = _make_handlers(db)
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
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """List documents with optional filters, paginated."""
    _, query_handler = _make_handlers(db)
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
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get document metadata with a presigned download URL."""
    _, query_handler = _make_handlers(db)
    result = await query_handler.get(document_id=document_id, clan_id=clan_id)
    return {"data": result.model_dump()}


@router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Delete a document from storage and the database (admin only)."""
    cmd_handler, _ = _make_handlers(db)
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
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Set a photo document as the person's avatar."""
    cmd_handler, _ = _make_handlers(db)
    await cmd_handler.set_avatar(document_id=document_id, clan_id=clan_id)
    return {"data": {"message": "Avatar set", "document_id": str(document_id)}}
