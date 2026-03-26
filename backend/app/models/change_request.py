"""ChangeRequest ORM model — configurable cross-approval workflow."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from app.models.base import Base


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clans.id", ondelete="CASCADE"),
        index=True,
    )

    requester_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    # create, update, delete
    action: Mapped[str] = mapped_column(String(20))
    # person, marriage, parent_child, event, document
    resource_type: Mapped[str] = mapped_column(String(50))
    # NULL for create; existing id for update/delete
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)

    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)

    # pending, approved, rejected
    status: Mapped[str] = mapped_column(String(20), default="pending")

    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    review_notes: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # ── ORM Relationships ─────────────────────────────────────
    clan = relationship("Clan")
