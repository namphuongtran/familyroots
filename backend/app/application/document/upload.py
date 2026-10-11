"""Direct-to-Storage document upload: sign, then confirm (ADR-068).

The browser uploads a document's bytes straight to Supabase Storage, so no byte
passes through the API, and Vercel's 4.5 MB request-body limit no longer caps a
document (ADR-065 § 6). The API's part is two calls:

1. ``sign`` checks the client's declared name, type and size, then mints a signed URL
   for one staged path, ``clans/{clan}/uploads/{uuid}.{ext}``.
2. ``confirm`` takes that path back. The path must have exactly the shape the server
   signs, under the acting clan. Then the handler reads what Storage really holds,
   checks it again, moves it into ``documents/``, and saves the row.

A staged file that is never confirmed is swept by the retention purge job.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from app.application.document.handlers import _presign_expiry
from app.domain.document.entity import DEFAULT_MAX_FILE_SIZE_BYTES, Document, check_upload_file
from app.domain.document.repository import (
    SIGNED_UPLOAD_TTL,
    DocumentRepository,
    StagedUploadStorage,
    StorageError,
    StorageNotFoundError,
)
from app.domain.document.storage_paths import (
    document_path,
    parse_staged_upload_path,
    safe_extension,
    staged_upload_path,
)
from app.domain.shared.exceptions import EntityNotFoundError, ValidationError
from app.domain.shared.unit_of_work import UnitOfWork
from app.domain.shared.value_objects import ActorInfo
from app.schemas.document import DocumentResponse, SignedUploadResponse

logger = logging.getLogger(__name__)


class DocumentUploadHandler:
    """Signs a staged upload, and turns a confirmed one into a document."""

    def __init__(
        self, repo: DocumentRepository, storage: StagedUploadStorage, uow: UnitOfWork
    ) -> None:
        self._repo = repo
        self._storage = storage
        self._uow = uow

    async def sign(
        self,
        *,
        clan_id: uuid.UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ) -> SignedUploadResponse:
        """Refuse a file that breaks the rules before any byte is sent; else sign."""
        check_upload_file(
            mime_type=content_type, size_bytes=size_bytes, max_file_size_bytes=max_file_size_bytes
        )
        path = staged_upload_path(clan_id, uuid.uuid4(), safe_extension(filename))

        # ADR-028: the auth dependencies read the database on this session, so a
        # transaction is open. End it before the Storage round trip below.
        await self._uow.rollback()
        signed = await self._storage.create_signed_upload(path)
        return SignedUploadResponse(
            storage_path=path,
            upload_url=signed.upload_url,
            token=signed.token,
            expires_at=datetime.now(UTC) + timedelta(seconds=SIGNED_UPLOAD_TTL),
        )

    async def confirm(
        self,
        *,
        clan_id: uuid.UUID,
        actor: ActorInfo,
        storage_path: str,
        title: str,
        document_type: str,
        original_filename: str | None = None,
        person_id: uuid.UUID | None = None,
        description: str | None = None,
        taken_date: date | None = None,
        taken_place: str | None = None,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ) -> DocumentResponse:
        """Turn a staged upload of this clan into a document."""
        # Clan isolation: the client sends this path back, so it is checked against
        # the acting clan before anything reads Storage. Another clan's path, a
        # confirmed document's path and any traversal all stop here.
        parsed = parse_staged_upload_path(storage_path, clan_id)
        if parsed is None:
            raise ValidationError("document.upload_path_invalid")
        file_id, extension = parsed

        # A body-supplied person_id must belong to the acting clan, so a document
        # can't link (or be filed under) a person owned by another clan.
        if person_id and not await self._repo.person_in_clan(person_id, clan_id):
            raise EntityNotFoundError("person_not_found", {"person_id": str(person_id)})

        # ADR-028: release the read transaction before the Storage calls below.
        await self._uow.rollback()

        try:
            stored = await self._storage.stat(storage_path)
        except StorageNotFoundError:
            # Never uploaded, already confirmed (the move took it), or swept.
            raise EntityNotFoundError("document.upload_not_found") from None

        # The check that counts: what Storage holds, not what the client declared at
        # signing. A file that fails it is deleted, so it cannot be confirmed later.
        try:
            check_upload_file(
                mime_type=stored.content_type,
                size_bytes=stored.size_bytes,
                max_file_size_bytes=max_file_size_bytes,
            )
        except ValidationError:
            await self._discard(storage_path)
            raise

        destination = document_path(clan_id, file_id, extension)
        doc = Document.create(
            clan_id=clan_id,
            actor=actor,
            title=title,
            document_type=document_type,
            storage_path=destination,
            mime_type=stored.content_type,
            file_size_bytes=stored.size_bytes,
            original_filename=original_filename,
            person_id=person_id,
            description=description,
            taken_date=taken_date,
            taken_place=taken_place,
            max_file_size_bytes=max_file_size_bytes,
        )

        try:
            await self._storage.move(storage_path, destination)
        except StorageNotFoundError:
            # A concurrent confirm of the same path moved it first.
            raise EntityNotFoundError("document.upload_not_found") from None

        # Blob first, then metadata. If persistence fails, delete the moved blob before
        # re-raising, so neither an orphan blob nor a dangling row survives.
        try:
            await self._repo.save(doc)
            await self._uow.commit()
        except Exception:
            # Best-effort: a cleanup failure must never mask the persistence error.
            try:
                await self._storage.delete(destination)
            except StorageError:
                logger.warning("Orphaned blob after failed upload commit: %s", destination)
            raise

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
            presigned_url_expires_at=_presign_expiry(),
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

    async def _discard(self, storage_path: str) -> None:
        try:
            await self._storage.delete(storage_path)
        except StorageError:
            # The sweep removes it within a day; the refusal still stands.
            logger.warning("Could not delete refused staged upload: %s", storage_path)
