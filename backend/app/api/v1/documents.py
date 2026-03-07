"""Documents API routes — upload, list, delete documents and photos."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.core.pagination import build_page, paginate_query
from app.core.permissions import ClanRole, RequireAdmin, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.member import Member
from app.schemas.document import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_BYTES,
    DocumentResponse,
    DocumentSummary,
)
from app.services.storage import delete_file, get_presigned_url, upload_file

router = APIRouter()


@router.post("", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: str = Form(...),
    member_id: uuid.UUID | None = Form(None),
    description: str | None = Form(None),
    taken_date: date | None = Form(None),
    taken_place: str | None = Form(None),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Upload a document/photo to Supabase Storage and save metadata."""
    actor_id = uuid.UUID(current_user["sub"])

    # Validate mime type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise ValidationError("invalid_mime_type", {"allowed": list(ALLOWED_MIME_TYPES)})

    # Validate document_type
    valid_types = {"photo", "id_document", "certificate", "audio", "video", "other"}
    if document_type not in valid_types:
        raise ValidationError("invalid_document_type")

    # Read file content and validate size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise ValidationError("file_too_large", {"max_bytes": MAX_FILE_SIZE_BYTES})

    # Verify member belongs to clan if provided
    if member_id:
        result = await db.execute(
            select(Member).where(
                Member.id == member_id,
                Member.clan_id == clan_id,
                Member.is_deleted.is_(False),
            )
        )
        if not result.scalar_one_or_none():
            raise NotFoundError("member_not_found")

    # Build storage path
    file_ext = (file.filename or "file").rsplit(".", 1)[-1] if file.filename else "bin"
    file_id = uuid.uuid4()
    storage_path = f"clans/{clan_id}/documents/{file_id}.{file_ext}"

    await upload_file(storage_path, content, file.content_type)

    doc = Document(
        clan_id=clan_id,
        member_id=member_id,
        title=title,
        description=description,
        document_type=document_type,
        storage_path=storage_path,
        file_size_bytes=len(content),
        mime_type=file.content_type,
        original_filename=file.filename,
        taken_date=taken_date,
        taken_place=taken_place,
        created_by=actor_id,
    )
    db.add(doc)
    db.add(AuditLog(
        clan_id=clan_id,
        actor_id=actor_id,
        actor_role="editor",
        action="document.upload",
        resource_type="document",
        resource_id=doc.id,
    ))
    await db.commit()
    await db.refresh(doc)

    presigned = await get_presigned_url(doc.storage_path)
    resp = DocumentResponse.model_validate(doc).model_dump()
    resp["presigned_url"] = presigned
    resp["presigned_url_expires_at"] = datetime.now(UTC).isoformat()
    return {"data": resp}


@router.get("")
async def list_documents(
    member_id: uuid.UUID | None = Query(None),
    document_type: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """List documents with optional filters, paginated."""
    query = select(Document).where(Document.clan_id == clan_id)
    if member_id:
        query = query.where(Document.member_id == member_id)
    if document_type:
        query = query.where(Document.document_type == document_type)

    query = paginate_query(query, Document, cursor, limit)
    result = await db.execute(query)
    docs = list(result.scalars().all())

    page = build_page(docs, limit)
    page["data"] = [DocumentSummary.model_validate(d).model_dump() for d in page["data"]]
    return page


@router.get("/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get document metadata with a presigned download URL."""
    doc = await _get_doc_or_404(document_id, clan_id, db)
    presigned = await get_presigned_url(doc.storage_path)
    resp = DocumentResponse.model_validate(doc).model_dump()
    resp["presigned_url"] = presigned
    return {"data": resp}


@router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Delete a document from storage and the database (admin only)."""
    doc = await _get_doc_or_404(document_id, clan_id, db)

    # Remove from storage
    await delete_file(doc.storage_path)

    # If this was an avatar, clear the member's avatar_url
    if doc.is_avatar and doc.member_id:
        result = await db.execute(
            select(Member).where(Member.id == doc.member_id)
        )
        member = result.scalar_one_or_none()
        if member:
            member.avatar_url = None

    await db.delete(doc)
    db.add(AuditLog(
        clan_id=clan_id,
        actor_id=uuid.UUID(current_user["sub"]),
        actor_role="admin",
        action="document.delete",
        resource_type="document",
        resource_id=document_id,
    ))
    await db.commit()
    return {"data": {"message": "Document deleted", "id": str(document_id)}}


@router.patch("/{document_id}/set-avatar")
async def set_document_as_avatar(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Set a photo document as the member's avatar."""
    doc = await _get_doc_or_404(document_id, clan_id, db)

    if not doc.member_id:
        raise ValidationError("document_not_linked_to_member")
    if doc.document_type != "photo":
        raise ValidationError("only_photo_can_be_avatar")

    # Unset existing avatar for this member
    existing = await db.execute(
        select(Document).where(
            Document.clan_id == clan_id,
            Document.member_id == doc.member_id,
            Document.is_avatar.is_(True),
            Document.id != doc.id,
        )
    )
    for old_avatar in existing.scalars().all():
        old_avatar.is_avatar = False

    doc.is_avatar = True

    # Update the member's avatar_url
    presigned = await get_presigned_url(doc.storage_path, expires_in=86400 * 30)
    result = await db.execute(
        select(Member).where(Member.id == doc.member_id)
    )
    member = result.scalar_one_or_none()
    if member:
        member.avatar_url = presigned

    await db.commit()
    return {"data": {"message": "Avatar set", "document_id": str(document_id)}}


async def _get_doc_or_404(
    doc_id: uuid.UUID, clan_id: uuid.UUID, db: AsyncSession
) -> Document:
    result = await db.execute(
        select(Document).where(
            Document.id == doc_id, Document.clan_id == clan_id
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("document_not_found")
    return doc
