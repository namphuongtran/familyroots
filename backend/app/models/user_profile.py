"""UserProfile ORM model — local cache of Supabase Auth user data.

Created lazily on first login via ``ensure_user_profile()`` in security.py.
The primary key ``id`` is the Supabase ``auth.users.id`` UUID (JWT ``sub`` claim).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class UserProfile(TimestampMixin, Base):
    __tablename__ = "user_profiles"

    # PK = Supabase auth.users.id (not auto-generated)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    avatar_url: Mapped[str | None] = mapped_column(String(500), default=None)
    language: Mapped[str] = mapped_column(String(10), default="vi")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Ho_Chi_Minh")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Platform-level role (user | super_admin).
    # Values: "user" (default) | "super_admin"
    platform_role: Mapped[str] = mapped_column(String(50), default="user")

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    # Canonical link to this user's person record (1:1, nullable)
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="SET NULL"),
        unique=True,
        default=None,
    )

    # ── ORM Relationships ─────────────────────────────────────
    person = relationship("Person", back_populates="user_profile", uselist=False)
    user_roles = relationship("UserClanRole", back_populates="user_profile", lazy="selectin")
    devices = relationship("UserDevice", back_populates="user_profile", lazy="selectin")
