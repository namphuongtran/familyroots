"""UserFcmToken ORM model — one push token per device, owned by a user.

The FCM repository and notification service access this table via raw SQL; the ORM
model exists so autogenerate drift detection sees the table and its columns. Schema
matches migration 004_fcm_tokens (and the runtime SQL: token, device_platform).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserFcmToken(Base):
    __tablename__ = "user_fcm_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    token: Mapped[str] = mapped_column(Text, unique=True)
    device_platform: Mapped[str | None] = mapped_column(String(20), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
