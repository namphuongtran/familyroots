"""ClanMembership ORM model — M:N link between Person and Clan."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from app.models.base import Base, TimestampMixin


class ClanMembership(TimestampMixin, Base):
    __tablename__ = "clan_memberships"
    # Explicit name matches the baseline migration; the uq naming convention would
    # otherwise generate uq_clan_memberships_person_id and drift on autogenerate.
    __table_args__ = (
        UniqueConstraint("person_id", "clan_id", name="uq_clan_memberships_person_clan"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="CASCADE"),
        index=True,
    )
    clan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clans.id", ondelete="RESTRICT"),
        index=True,
    )

    # blood = con cháu ruột, spouse = dâu/rể, adopted = con nuôi
    role: Mapped[str] = mapped_column(String(20), default="blood")

    # Generation number within this clan (relative, not absolute)
    generation: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    is_founder: Mapped[bool] = mapped_column(Boolean, default=False)

    # Branch within this clan (chi/phái)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="SET NULL"),
        default=None,
        index=True,
    )

    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # ── ORM Relationships ─────────────────────────────────────
    person = relationship("Person", back_populates="clan_memberships")
    clan = relationship("Clan", back_populates="clan_memberships")
    branch = relationship("Branch", back_populates="members")
