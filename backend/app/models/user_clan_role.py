"""UserClanRole ORM model — maps Supabase Auth users to clans with roles."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class UserClanRole(TimestampMixin, Base):
    __tablename__ = "user_clan_roles"
    # (user_id, clan_id) uniqueness is enforced by the unique INDEX
    # idx_user_clan_roles_user_clan (baseline migration), not a table constraint —
    # declaring a UniqueConstraint here would make autogenerate add a redundant one.

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clans.id", ondelete="RESTRICT"),
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)

    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)

    # ORM relationships
    clan = relationship("Clan", back_populates="user_roles")
    user_profile = relationship("UserProfile", back_populates="user_roles")
