"""Document ORM model — photos, certificates, audio/video attached to a person."""

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from app.models.base import Base, ClanScopedMixin


class Document(ClanScopedMixin, Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="SET NULL"),
        default=None,
    )

    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    # 'photo','id_document','certificate',...
    document_type: Mapped[str] = mapped_column(String(20))

    # Supabase Storage
    storage_path: Mapped[str] = mapped_column(String(500), unique=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, default=None)
    mime_type: Mapped[str | None] = mapped_column(String(100), default=None)
    original_filename: Mapped[str | None] = mapped_column(String(255), default=None)

    # For photos: optional metadata
    taken_date: Mapped[date | None] = mapped_column(Date, default=None)
    taken_place: Mapped[str | None] = mapped_column(String(255), default=None)

    is_avatar: Mapped[bool] = mapped_column(Boolean, default=False)

    # Soft delete (ADR-019): rows are recoverable until the retention purge job
    # removes blob + row after DOCUMENT_RETENTION_DAYS.
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)

    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    # ORM relationships
    person = relationship("Person", back_populates="documents")
