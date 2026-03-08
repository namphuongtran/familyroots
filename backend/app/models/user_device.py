"""UserDevice ORM model — tracks FCM tokens per user device."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UserDevice(Base):
    __tablename__ = "user_devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    fcm_token: Mapped[str] = mapped_column(String(500), unique=True)
    device_name: Mapped[str | None] = mapped_column(String(255), default=None)
    platform: Mapped[str] = mapped_column(String(20))  # ios, android, web
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # ── ORM Relationships ─────────────────────────────────────
    user_profile = relationship("UserProfile", back_populates="devices")
