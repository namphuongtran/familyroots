"""Document use-case handlers.

Orchestrate document upload, listing, deletion, and avatar management
through domain entities, repository protocol, and storage port.
No SQLAlchemy or Supabase imports — fully DIP-compliant.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.domain.document.entity import Document
from app.domain.document.repository import DocumentRepository, StoragePort
from app.domain.shared.exceptions import EntityNotFoundError
from app.domain.shared.unit_of_work import UnitOfWork
from app.domain.shared.value_objects import ActorInfo
from app.schemas.document import DocumentResponse, DocumentSummary


class DocumentCommandHandler:
    """Handles document write operations."""

    def __init__(
        self,
        repo: DocumentRepository,
        storage: StoragePort,
        uow: UnitOfWork,
    ) -> None:
        self._repo = repo
        self._storage = storage
        self._uow = uow

    async def upload(
        self,
        *,
        file_content: bytes,
        filename: str | None,
        content_type: str | None,
        title: str,
        document_type: str,
        clan_id: uuid.UUID,
        actor: ActorInfo,
        person_id: uuid.UUID | None = None,
        description: str | None = None,
        taken_date: Any = None,
        taken_place: str | None = None,
    ) -> DocumentResponse:
        """Upload a document to storage and save metadata."""
        file_ext = (filename or "file").rsplit(".", 1)[-1] if filename else "bin"
        file_id = uuid.uuid4()
        storage_path = f"clans/{clan_id}/documents/{file_id}.{file_ext}"

        # Domain entity creation validates MIME, size, and type
        doc = Document.create(
            clan_id=clan_id,
            actor=actor,
            title=title,
            document_type=document_type,
            storage_path=storage_path,
            mime_type=content_type,
            file_size_bytes=len(file_content),
            original_filename=filename,
            person_id=person_id,
            description=description,
            taken_date=taken_date,
            taken_place=taken_place,
        )

        # Upload to storage, then persist metadata
        await self._storage.upload(storage_path, file_content, content_type)
        await self._repo.save(doc)
        await self._uow.commit()

        presigned = await self._storage.get_presigned_url(doc.storage_path)
        return DocumentResponse(
            id=doc.id,
            clan_id=doc.clan_id,
            person_id=doc.person_id,
            title=doc.title,
            document_type=doc.document_type,
            description=doc.description,
            storage_path=doc.storage_path,
            presigned_url=presigned,
            presigned_url_expires_at=datetime.now(UTC).isoformat(),
            file_size_bytes=doc.file_size_bytes,
            mime_type=doc.mime_type,
            original_filename=doc.original_filename,
            taken_date=doc.taken_date,
            taken_place=doc.taken_place,
            is_avatar=doc.is_avatar,
            created_by=doc.created_by,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    async def delete(
        self,
        *,
        document_id: uuid.UUID,
        clan_id: uuid.UUID,
        actor: ActorInfo,
    ) -> None:
        """Delete a document from storage and the database."""
        doc = await self._get_or_raise(document_id, clan_id)
        await self._storage.delete(doc.storage_path)
        doc.mark_deleted(actor)
        await self._repo.delete(doc)
        await self._uow.commit()

    async def set_avatar(
        self,
        *,
        document_id: uuid.UUID,
        clan_id: uuid.UUID,
    ) -> str | None:
        """Set a photo document as the person's avatar. Returns presigned URL."""
        doc = await self._get_or_raise(document_id, clan_id)
        doc.set_avatar()  # validates person linkage and type

        # Clear old avatars
        old_avatars = await self._repo.get_person_avatars(
            clan_id,
            doc.person_id,  # type: ignore[arg-type]
            doc.id,
        )
        for old in old_avatars:
            old.unset_avatar()
            await self._repo.save(old)

        await self._repo.save(doc)

        presigned = await self._storage.get_presigned_url(doc.storage_path, expires_in=86400 * 30)
        await self._uow.commit()
        return presigned

    async def _get_or_raise(self, doc_id: uuid.UUID, clan_id: uuid.UUID) -> Document:
        doc = await self._repo.get_by_id(doc_id, clan_id)
        if not doc:
            raise EntityNotFoundError("document_not_found")
        return doc


class DocumentQueryHandler:
    """Read-only handler for document queries."""

    def __init__(self, repo: DocumentRepository, storage: StoragePort) -> None:
        self._repo = repo
        self._storage = storage

    async def get(self, *, document_id: uuid.UUID, clan_id: uuid.UUID) -> DocumentResponse:
        """Get document metadata with a presigned download URL."""
        doc = await self._repo.get_by_id(document_id, clan_id)
        if not doc:
            raise EntityNotFoundError("document_not_found")

        presigned = await self._storage.get_presigned_url(doc.storage_path)
        return DocumentResponse(
            id=doc.id,
            clan_id=doc.clan_id,
            person_id=doc.person_id,
            title=doc.title,
            document_type=doc.document_type,
            description=doc.description,
            storage_path=doc.storage_path,
            presigned_url=presigned,
            file_size_bytes=doc.file_size_bytes,
            mime_type=doc.mime_type,
            original_filename=doc.original_filename,
            taken_date=doc.taken_date,
            taken_place=doc.taken_place,
            is_avatar=doc.is_avatar,
            created_by=doc.created_by,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    async def list_documents(
        self,
        *,
        clan_id: uuid.UUID,
        person_id: uuid.UUID | None = None,
        document_type: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[DocumentSummary]:
        """List documents with optional filters."""
        docs = await self._repo.list_in_clan(
            clan_id,
            person_id=person_id,
            document_type=document_type,
            cursor=cursor,
            limit=limit,
        )
        return [
            DocumentSummary(
                id=d.id,
                title=d.title,
                document_type=d.document_type,
                mime_type=d.mime_type,
                file_size_bytes=d.file_size_bytes,
                is_avatar=d.is_avatar,
                created_at=d.created_at,
            )
            for d in docs
        ]
