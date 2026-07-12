"""Repository protocol and storage port for the Document bounded context."""

from __future__ import annotations

import uuid
from typing import Protocol

from app.domain.document.entity import Document


class DocumentRepository(Protocol):
    """Abstract persistence contract for Document entities."""

    async def get_by_id(self, document_id: uuid.UUID, clan_id: uuid.UUID) -> Document | None:
        """Fetch a non-deleted document by ID within a clan."""
        ...

    async def get_deleted(self, document_id: uuid.UUID, clan_id: uuid.UUID) -> Document | None:
        """Fetch a soft-deleted document by ID within a clan (for restore)."""
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

    async def person_in_clan(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> bool:
        """Whether a person has a membership in the given clan (guards body-supplied
        person_id on upload so a document can't link a person from another clan)."""
        ...

    async def save(self, doc: Document) -> None:
        """Insert or update a Document entity.

        Soft-delete (ADR-019) also flows through ``save``: callers call
        ``doc.mark_deleted(actor)`` then ``save(doc)`` — there is no separate
        ``delete`` method. The row and blob both survive until the retention
        purge job (``app.services.document_purge``) removes them.
        """
        ...


DEFAULT_PRESIGN_TTL = 3600  # seconds — default presigned-URL lifetime


class StorageError(Exception):
    """Base class for storage-adapter failures (provider-agnostic)."""


class StorageUnavailableError(StorageError):
    """Storage backend unreachable or misconfigured — surfaced as HTTP 503.

    Covers provider 5xx, transport failures (DNS/connection/TLS/timeout), and a
    rejected API key (our configuration). Never conflate an outage with a code
    bug (500) or with a missing object (404)."""


class StorageNotFoundError(StorageError):
    """The requested storage object does not exist — surfaced as HTTP 404."""


class StoragePort(Protocol):
    """Abstract storage contract — decouples from Supabase."""

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        """Upload a file, return the storage path."""
        ...

    async def delete(self, storage_path: str) -> bool:
        """Delete a file by path. Returns True on success."""
        ...

    async def get_presigned_url(
        self, storage_path: str, expires_in: int = DEFAULT_PRESIGN_TTL
    ) -> str:
        """Generate a time-limited presigned URL."""
        ...
