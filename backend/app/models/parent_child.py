"""ParentChild ORM model — global edge linking parent to child."""

import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from app.models.base import Base, TimestampMixin


class ParentChild(TimestampMixin, Base):
    __tablename__ = "parent_child"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    parent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="CASCADE"),
        index=True,
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="CASCADE"),
        index=True,
    )

    # Clan that created/manages this record (for write RLS)
    created_by_clan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clans.id", ondelete="CASCADE"),
        index=True,
    )

    # biological, adopted, step, foster
    relationship_type: Mapped[str] = mapped_column(
        String(20), default="biological"
    )

    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    # ── ORM Relationships ─────────────────────────────────────
    parent = relationship(
        "Person",
        foreign_keys=[parent_id],
        back_populates="parent_links",
    )
    child = relationship(
        "Person",
        foreign_keys=[child_id],
        back_populates="child_links",
    )
    managing_clan = relationship("Clan")
