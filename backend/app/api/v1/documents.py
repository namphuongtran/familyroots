"""Documents API routes — thin controller delegating to Document handlers."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.application.document.handlers import DocumentCommandHandler, DocumentQueryHandler
from app.application.document.upload import DocumentUploadHandler
from app.core.config import settings
from app.core.permissions import ClanRole, RequireAdmin, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.dependencies import (
    get_document_command_handler,
    get_document_query_handler,
    get_document_upload_handler,
)
from app.schemas.document import (
    DocumentCreateRequest,
    DocumentResponse,
    SignedUploadResponse,
    SignUploadRequest,
)
from app.schemas.envelope import created, ok, ok_message, page
from app.services.translator import t

router = APIRouter()


@router.post("/uploads", responses=ok(SignedUploadResponse))
async def sign_document_upload(
    body: SignUploadRequest,
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    upload_handler: DocumentUploadHandler = Depends(get_document_upload_handler),
    role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Sign a direct-to-Storage upload of one file (ADR-068).

    The file is checked against the declared name, type and size first, so a file
    that breaks a rule is refused before any byte is sent. The client then uploads
    the bytes to `upload_url` and confirms with `POST /documents`.
    """
    result = await upload_handler.sign(
        clan_id=clan_id,
        filename=body.filename,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        max_file_size_bytes=settings.max_upload_bytes,
    )
    return {"data": result.model_dump()}


@router.post("", status_code=201, responses=created(DocumentResponse))
async def create_document(
    body: DocumentCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    upload_handler: DocumentUploadHandler = Depends(get_document_upload_handler),
    role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Confirm a staged upload as a document, checking what Storage really holds."""
    result = await upload_handler.confirm(
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, role.value),
        storage_path=body.storage_path,
        title=body.title,
        document_type=body.document_type,
        original_filename=body.original_filename,
        person_id=body.person_id,
        description=body.description,
        taken_date=body.taken_date,
        taken_place=body.taken_place,
        max_file_size_bytes=settings.max_upload_bytes,
    )
    return {"data": result.model_dump()}


@router.get("", responses=page(DocumentResponse))
async def list_documents(
    person_id: uuid.UUID | None = Query(None),
    document_type: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: DocumentQueryHandler = Depends(get_document_query_handler),
    role: ClanRole = RequireViewer,
    fields: str | None = Query(None),
) -> dict[str, Any]:
    """List documents with optional filters, paginated."""
    items, meta = await query_handler.list_documents(
        clan_id=clan_id,
        person_id=person_id,
        document_type=document_type,
        cursor=cursor,
        limit=limit,
    )
    data = [item.model_dump() for item in items]
    if fields:
        field_set = {f.strip() for f in fields.split(",")}
        data = [{k: v for k, v in d.items() if k in field_set} for d in data]
    return {"data": data, "meta": meta}


@router.get("/{document_id}", responses=ok(DocumentResponse))
async def get_document(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: DocumentQueryHandler = Depends(get_document_query_handler),
    role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get document metadata with a presigned download URL."""
    result = await query_handler.get(document_id=document_id, clan_id=clan_id)
    return {"data": result.model_dump()}


@router.delete("/{document_id}", responses=ok_message())
async def delete_document(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: DocumentCommandHandler = Depends(get_document_command_handler),
    role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Delete a document from storage and the database (admin only)."""
    await cmd_handler.delete(
        document_id=document_id,
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, role.value),
    )
    return {"data": {"message": t("document.deleted"), "id": str(document_id)}}


@router.post("/{document_id}/restore", responses=ok(DocumentResponse))
async def restore_document(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: DocumentCommandHandler = Depends(get_document_command_handler),
    role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Restore a soft-deleted document (admin only)."""
    result = await cmd_handler.restore(
        document_id=document_id,
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, role.value),
    )
    return {"data": result.model_dump()}


@router.patch("/{document_id}/set-avatar", responses=ok_message())
async def set_document_as_avatar(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: DocumentCommandHandler = Depends(get_document_command_handler),
    role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Set a photo document as the person's avatar.

    Publishes the image to the public avatars bucket and stamps the resulting
    permanent URL onto `persons.avatar_url` (ADR-036). `avatar_url` is returned so a
    client can render immediately without re-reading the person; it is the same value
    every person/tree response now carries.
    """
    avatar_url = await cmd_handler.set_avatar(
        document_id=document_id,
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, role.value),
    )
    return {
        "data": {
            "message": t("document.avatar_set"),
            "document_id": str(document_id),
            "avatar_url": avatar_url,
        }
    }
