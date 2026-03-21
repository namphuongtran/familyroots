"""Repository protocol and storage port for the Document bounded context."""

from __future__ import annotations

import uuid
from typing import Protocol

from app.domain.document.entity import Document


class DocumentRepository(Protocol):
    """Abstract persistence contract for Document entities."""

    async def get_by_id(self, document_id: uuid.UUID, clan_id: uuid.UUID) -> Document | None:
        """Fetch a document by ID within a clan."""
        ...

    async def list_in_clan(
        self,
        clan_id: uuid.UUID,
        *,
        person_id: uuid.UUID | None = None,
        document_type: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[Document]:
        """List documents in a clan with optional filters."""
        ...

    async def get_person_avatars(
        self,
        clan_id: uuid.UUID,
        person_id: uuid.UUID,
        exclude_id: uuid.UUID,
    ) -> list[Document]:
        """Get current avatar documents for a person (for clearing old avatars)."""
        ...

    async def save(self, doc: Document) -> None:
        """Insert or update a Document entity."""
        ...

    async def delete(self, doc: Document) -> None:
        """Hard-delete a document."""
        ...


class StoragePort(Protocol):
    """Abstract storage contract — decouples from Supabase."""

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        """Upload a file, return the storage path."""
        ...

    async def delete(self, storage_path: str) -> bool:
        """Delete a file by path. Returns True on success."""
        ...

    async def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """Generate a time-limited presigned URL."""
        ...
