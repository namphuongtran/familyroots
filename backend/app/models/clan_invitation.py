"""ClanInvitation ORM model — tracks pending clan invitations."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ClanInvitation(Base):
    __tablename__ = "clan_invitations"
    __table_args__ = (Index("ix_clan_invitations_clan_email", "clan_id", "email"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clans.id", ondelete="CASCADE"),
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    invited_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    token: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # ── ORM Relationships ─────────────────────────────────────
    clan = relationship("Clan")
