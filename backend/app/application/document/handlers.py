"""Document use-case handlers.

Orchestrate document upload, listing, deletion, and avatar management
through domain entities, repository protocol, and storage port.
No SQLAlchemy or Supabase imports — fully DIP-compliant.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.application.shared.audit import emit_audit_event
from app.domain.document.entity import DEFAULT_MAX_FILE_SIZE_BYTES, Document
from app.domain.document.repository import (
    DEFAULT_PRESIGN_TTL,
    DocumentRepository,
    StorageError,
    StoragePort,
)
from app.domain.person.repository import PersonRepository
from app.domain.shared.exceptions import BusinessRuleViolation, EntityNotFoundError
from app.domain.shared.unit_of_work import UnitOfWork
from app.domain.shared.value_objects import ActorInfo
from app.schemas.document import DocumentResponse, DocumentSummary

logger = logging.getLogger(__name__)


def _safe_extension(filename: str | None) -> str:
    """Derive a storage-safe file extension from a client-supplied filename.

    The extension is embedded in the storage key `clans/{clan_id}/documents/...`,
    whose prefix is the storage tenancy boundary. A raw filename can contain
    `/` or `..` (e.g. ``x.jpg/../../other-clan/evil``) and escape that prefix, so
    we keep only lowercase alphanumerics from the last dot-segment. Falls back to
    ``bin`` when there is no usable extension.
    """
    if not filename or "." not in filename:
        return "bin"
    raw = filename.rsplit(".", 1)[-1]
    cleaned = re.sub(r"[^a-z0-9]", "", raw.lower())[:10]
    return cleaned or "bin"


def _presign_expiry(expires_in: int = DEFAULT_PRESIGN_TTL) -> datetime:
    """Absolute expiry of a presigned URL minted *now*.

    Every response that carries a `presigned_url` must carry the matching
    `presigned_url_expires_at`: the provider signs relative to generation time,
    so only the backend can state the wall-clock deadline. Before this helper
    only the upload path computed it and the read paths returned `null`, which
    forced clients to hardcode a guessed TTL (frontend-integration-guide §8).
    """
    return datetime.now(UTC) + timedelta(seconds=expires_in)


def _avatar_object_path(clan_id: uuid.UUID, person_id: uuid.UUID) -> str:
    """The public avatars bucket key for one person, as seen by one clan (ADR-036).

    Clan-prefixed exactly like the private document keys, so the storage tenancy
    boundary is identical in both buckets — a public bucket is the last place a path
    should stop being clan-scoped. Both ids come from server state (the authenticated
    clan header and the document's own person link), never from client input, so
    there is nothing to sanitize the way ``_safe_extension`` must.

    Deliberately extension-less and stable per person: replacing someone's avatar
    upserts the same object, so the stored URL never changes and no orphan copies
    accumulate. The browser gets the format from the stored Content-Type.
    """
    return f"clans/{clan_id}/avatars/{person_id}"


class DocumentCommandHandler:
    """Handles document write operations."""

    def __init__(
        self,
        repo: DocumentRepository,
        storage: StoragePort,
        uow: UnitOfWork,
        person_repo: PersonRepository,
    ) -> None:
        self._repo = repo
        self._storage = storage
        self._uow = uow
        # set_avatar writes persons.avatar_url, which belongs to the Person aggregate.
        # It goes through the Person repository + Person domain method (not a raw
        # UPDATE from here) so the write still emits PersonUpdated and lands in the
        # same UoW transaction as the document change.
        self._person_repo = person_repo

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
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ) -> DocumentResponse:
        """Upload a document to storage and save metadata."""
        # A body-supplied person_id must belong to the acting clan, so a document
        # can't link (or be filed under) a person owned by another clan.
        if person_id and not await self._repo.person_in_clan(person_id, clan_id):
            raise EntityNotFoundError("person_not_found", {"person_id": str(person_id)})

        # ADR-028: end the read transaction so the multi-second Supabase blob
        # upload below holds NO pooled connection (H5). A None person_id skips
        # the read above; rollback() is then a no-op. The read has nothing to
        # persist, so rollback (not commit) is the cheap way to release.
        await self._uow.rollback()

        file_ext = _safe_extension(filename)
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
            max_file_size_bytes=max_file_size_bytes,
        )

        # Upload the blob first, then persist metadata. If persistence fails, the
        # blob would be orphaned (a row-less object in the bucket), so compensate
        # by deleting it before re-raising — leaving neither an orphan blob nor a
        # dangling metadata row.
        await self._storage.upload(storage_path, file_content, content_type)
        try:
            await self._repo.save(doc)
            await self._uow.commit()
        except Exception:
            # Best-effort compensation — never let a cleanup failure mask the
            # original persistence error (which is what the caller must see).
            # storage.delete() now raises StorageError instead of returning
            # False on failure (FIX 2, task 3 review) — catch it so
            # compensation never raises.
            try:
                await self._storage.delete(storage_path)
            except StorageError:
                logger.warning("Orphaned blob after failed upload commit: %s", storage_path)
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

    async def delete(
        self,
        *,
        document_id: uuid.UUID,
        clan_id: uuid.UUID,
        actor: ActorInfo,
    ) -> None:
        """Soft-delete a document (ADR-019): the row is flagged, the blob is left
        untouched, and both survive until the retention purge job."""
        doc = await self._get_or_raise(document_id, clan_id)
        doc.mark_deleted(actor)
        await self._repo.save(doc)
        await self._uow.commit()

    async def restore(
        self,
        *,
        document_id: uuid.UUID,
        clan_id: uuid.UUID,
        actor: ActorInfo,
    ) -> DocumentResponse:
        """Restore a soft-deleted document."""
        doc = await self._repo.get_deleted(document_id, clan_id)
        if not doc:
            raise EntityNotFoundError("document_not_found")

        doc.restore(actor)
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

    async def set_avatar(
        self,
        *,
        document_id: uuid.UUID,
        clan_id: uuid.UUID,
        actor: ActorInfo,
    ) -> str:
        """Publish a photo document as the person's avatar; return its permanent URL.

        ADR-036. This is the ONLY writer of ``persons.avatar_url``. It publishes the
        image into the dedicated public avatars bucket under a stable clan-scoped
        path and stamps the resulting durable URL onto the person.

        It deliberately no longer mints a 30-day presigned URL. A presigned URL is
        exactly what must never land in that column: it expires, and the column then
        rots silently with nothing to notice or repair it.

        Ordering, and why it changed: the publish now gates the DB write, so a
        storage failure is a 503 and the avatar is simply not set. Previously
        set-avatar was a pure-DB write that tolerated a storage outage — it can't be
        any more, because "``is_avatar = true`` but no published object" is a
        half-applied state with a permanently wrong URL (or none) attached to a
        person. Failing closed is the only consistent option.
        """
        doc = await self._get_or_raise(document_id, clan_id)
        doc.set_avatar()  # validates person linkage and type
        person_id = doc.person_id
        assert person_id is not None  # guaranteed by Document.set_avatar()

        # Clan-isolation backstop before anything becomes world-readable. get_by_id is
        # already clan-scoped, so reaching here with a foreign clan_id or a storage key
        # outside this clan's prefix means the row is inconsistent with its own path —
        # refuse rather than copy another clan's object into a public bucket, where the
        # mistake would be irreversible and visible to strangers.
        if doc.clan_id != clan_id or not doc.storage_path.startswith(f"clans/{clan_id}/"):
            raise BusinessRuleViolation(
                "document.avatar_source_outside_clan", {"document_id": str(doc.id)}
            )

        # The person must be a live member of the acting clan (clan-scoped read). This
        # is also what stops clan B from stamping a URL onto a person it cannot see.
        person = await self._person_repo.get_in_clan(person_id, clan_id)
        if not person:
            raise EntityNotFoundError("person_not_found", {"person_id": str(person_id)})

        # ADR-028: release the pooled connection before the blob copy below. Nothing
        # is pending — everything so far was a read — so rollback is the cheap release.
        await self._uow.rollback()

        avatar_url = await self._storage.publish_public(
            source_path=doc.storage_path,
            destination_path=_avatar_object_path(clan_id, person_id),
            content_type=doc.mime_type,
        )

        # Blob is live and permanently addressable; now record it in one transaction.
        old_avatars = await self._repo.get_person_avatars(clan_id, person_id, doc.id)
        for old in old_avatars:
            old.unset_avatar()
            await self._repo.save(old)
        await self._repo.save(doc)

        # Person aggregate + domain event (PersonUpdated), not a raw column write, so
        # the avatar change is audited like every other person edit. set_avatar_url
        # re-checks that the URL is permanent — a presigned URL cannot get in even if
        # a future storage adapter returned one.
        person.set_avatar_url(avatar_url, actor, clan_id)
        await self._person_repo.save(person)

        # emit_audit_event commits: the document flags, the person URL, the
        # PersonUpdated audit row and this one all land in the same transaction.
        await emit_audit_event(
            self._uow,
            action="document.set_avatar",
            resource_type="document",
            resource_id=doc.id,
            actor=actor,
            clan_id=clan_id,
            new_value={
                "is_avatar": True,
                "person_id": str(person_id),
                "avatar_url": avatar_url,
            },
        )
        return avatar_url

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

    async def list_documents(
        self,
        *,
        clan_id: uuid.UUID,
        person_id: uuid.UUID | None = None,
        document_type: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[DocumentSummary], dict[str, Any]]:
        """List documents with optional filters. Returns (page items, cursor meta)."""
        from app.core.pagination import build_page

        # Repo fetches limit+1 (paginate_query); build_page slices to limit and
        # derives the next-page cursor from the trailing row.
        docs = await self._repo.list_in_clan(
            clan_id,
            person_id=person_id,
            document_type=document_type,
            cursor=cursor,
            limit=limit,
        )
        page = build_page(docs, limit)
        summaries = [
            DocumentSummary(
                id=d.id,
                title=d.title,
                document_type=d.document_type,
                mime_type=d.mime_type,
                file_size_bytes=d.file_size_bytes,
                is_avatar=d.is_avatar,
                created_at=d.created_at,
            )
            for d in page["data"]
        ]
        return summaries, page["meta"]
