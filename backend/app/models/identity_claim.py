"""IdentityClaim ORM model — tracks user requests to link their profile to a family tree person."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class IdentityClaim(TimestampMixin, Base):
    __tablename__ = "identity_claims"

    # Partial unique index to enforce that a user can only have ONE pending claim globally.
    __table_args__ = (
        Index(
            "uq_identity_claim_user_pending",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="CASCADE"),
        index=True,
    )

    # status: PENDING, APPROVED, REJECTED, CANCELLED
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)

    requester_note: Mapped[str | None] = mapped_column(Text, default=None)
    reviewer_note: Mapped[str | None] = mapped_column(Text, default=None)

    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="SET NULL"),
        default=None,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # ORM relationships
    user = relationship("UserProfile", foreign_keys=[user_id])
    person = relationship("Person")
    reviewer = relationship("UserProfile", foreign_keys=[reviewed_by])
