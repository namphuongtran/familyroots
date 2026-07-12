"""Document domain entity — pure Python, no framework dependencies.

The Document aggregate root encapsulates rules for clan documents:
type validation, MIME checking, size limits, and avatar management.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from app.domain.document.events import DocumentCreated, DocumentDeleted, DocumentRestored
from app.domain.shared.entity import AggregateRoot
from app.domain.shared.exceptions import BusinessRuleViolation, ValidationError
from app.domain.shared.value_objects import ActorInfo

_VALID_DOC_TYPES = frozenset({"photo", "id_document", "certificate", "audio", "video", "other"})

ALLOWED_MIME_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "application/pdf",
        "audio/mpeg",
        "audio/wav",
        "video/mp4",
        "video/quicktime",
    }
)

# The domain's default upload-size policy. It is the single source of the number:
# Settings.MAX_UPLOAD_SIZE_MB derives its default from this, and the application
# injects the (env-tunable) resolved limit into create() below. Kept in the domain
# (not app.core) so the domain enforces the invariant without importing config.
DEFAULT_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


@dataclass
class Document(AggregateRoot):
    """Document aggregate root.

    Represents a file (photo, certificate, audio…) attached to a clan or person.
    """

    # ── Identity ──────────────────────────────────────────────
    clan_id: uuid.UUID = field(default_factory=uuid.uuid4)
    person_id: uuid.UUID | None = None
    title: str = ""
    description: str | None = None
    document_type: str = "other"

    # ── Storage ───────────────────────────────────────────────
    storage_path: str = ""
    file_size_bytes: int | None = None
    mime_type: str | None = None
    original_filename: str | None = None

    # ── Photo metadata ────────────────────────────────────────
    taken_date: date | None = None
    taken_place: str | None = None
    is_avatar: bool = False

    # ── Audit ─────────────────────────────────────────────────
    created_by: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # ── Soft delete (ADR-019) ─────────────────────────────────
    is_deleted: bool = False
    deleted_at: datetime | None = None
    deleted_by: uuid.UUID | None = None

    # ── Domain methods ────────────────────────────────────────

    @classmethod
    def create(
        cls,
        *,
        clan_id: uuid.UUID,
        actor: ActorInfo,
        title: str,
        document_type: str,
        storage_path: str,
        mime_type: str | None = None,
        file_size_bytes: int | None = None,
        original_filename: str | None = None,
        person_id: uuid.UUID | None = None,
        description: str | None = None,
        taken_date: date | None = None,
        taken_place: str | None = None,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ) -> Document:
        """Factory method with upload validation.

        ``max_file_size_bytes`` is the resolved limit (the application injects the
        env-tunable value); it defaults to the domain policy so direct domain use
        stays safe.
        """
        if document_type not in _VALID_DOC_TYPES:
            raise ValidationError("invalid_document_type")
        if mime_type and mime_type not in ALLOWED_MIME_TYPES:
            raise ValidationError("invalid_mime_type", {"allowed": list(ALLOWED_MIME_TYPES)})
        if file_size_bytes and file_size_bytes > max_file_size_bytes:
            raise ValidationError("file_too_large", {"max_bytes": max_file_size_bytes})

        doc = cls(
            clan_id=clan_id,
            person_id=person_id,
            title=title,
            description=description,
            document_type=document_type,
            storage_path=storage_path,
            file_size_bytes=file_size_bytes,
            mime_type=mime_type,
            original_filename=original_filename,
            taken_date=taken_date,
            taken_place=taken_place,
            created_by=actor.user_id,
        )
        doc.add_event(
            DocumentCreated(
                document_id=doc.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                title=title,
                document_type=document_type,
            )
        )
        return doc

    def set_avatar(self) -> None:
        """Mark this document as the person's avatar."""
        if not self.person_id:
            raise BusinessRuleViolation("document_not_linked_to_person")
        if self.document_type != "photo":
            raise BusinessRuleViolation("only_photo_can_be_avatar")
        self.is_avatar = True

    def unset_avatar(self) -> None:
        """Remove avatar status from this document."""
        self.is_avatar = False

    def mark_deleted(self, actor: ActorInfo) -> None:
        """Soft-delete: the repository persists this state; the blob stays until
        the retention purge job (ADR-019)."""
        self.is_deleted = True
        self.deleted_at = datetime.now(UTC)
        self.deleted_by = actor.user_id
        self.add_event(
            DocumentDeleted(
                document_id=self.id,
                clan_id=self.clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
            )
        )

    def restore(self, actor: ActorInfo) -> None:
        """Restore a soft-deleted document."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.add_event(
            DocumentRestored(
                document_id=self.id,
                clan_id=self.clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
            )
        )
