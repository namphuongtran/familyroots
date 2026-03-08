"""ClanSettings ORM model — per-clan configuration (one row per clan)."""

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ClanSettings(TimestampMixin, Base):
    __tablename__ = "clan_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clans.id", ondelete="CASCADE"),
        unique=True,  # one settings row per clan
    )

    # Approval workflow configuration
    approval_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)

    default_language: Mapped[str] = mapped_column(String(10), default="vi")
    tree_display_mode: Mapped[str] = mapped_column(String(20), default="vertical")
    allow_public_tree: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_defaults: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    privacy_level: Mapped[str] = mapped_column(String(20), default="clan_members")
    max_upload_size_mb: Mapped[int] = mapped_column(SmallInteger, default=10)

    # ── ORM Relationships ─────────────────────────────────────
    clan = relationship("Clan", back_populates="settings")
