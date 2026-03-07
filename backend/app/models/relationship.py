"""Relationship ORM model — edge list for the family graph."""

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from app.models.base import Base, ClanScopedMixin


class Relationship(ClanScopedMixin, Base):
    __tablename__ = "relationships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
    )
    related_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
    )

    relation_type: Mapped[str] = mapped_column(String(20))       # 'parent', 'child', 'spouse'
    relation_subtype: Mapped[str] = mapped_column(String(20))    # 'biological', 'adoptive', etc.

    # For spouse relationships: marriage timeline
    start_date: Mapped[date | None] = mapped_column(Date, default=None)
    end_date: Mapped[date | None] = mapped_column(Date, default=None)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)

    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    # ORM relationships
    member = relationship(
        "Member", foreign_keys=[member_id], back_populates="relationships_as_member"
    )
    related = relationship(
        "Member", foreign_keys=[related_id], back_populates="relationships_as_related"
    )
