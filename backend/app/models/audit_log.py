"""AuditLog ORM model — immutable log of all write actions."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # nullable + SET NULL: platform-level actions have no clan, and deleting a clan
    # must not erase its audit trail. The FK (name fk_audit_logs_clan_id_clans via the
    # naming convention) matches the baseline migration — declare it so autogenerate
    # doesn't try to drop it.
    clan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clans.id", ondelete="SET NULL"), default=None
    )

    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    actor_role: Mapped[str] = mapped_column(String(50))

    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)

    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)

    ip_address: Mapped[str | None] = mapped_column(INET, default=None)
    user_agent: Mapped[str | None] = mapped_column(String(500), default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
