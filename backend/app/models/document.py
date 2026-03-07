"""Document ORM model — photos, certificates, audio/video attached to a member."""

import uuid
from datetime import date

from sqlalchemy import BigInteger, Boolean, Date, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from app.models.base import Base, ClanScopedMixin


class Document(ClanScopedMixin, Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="SET NULL"),
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

    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    # ORM relationships
    member = relationship("Member", back_populates="documents")
