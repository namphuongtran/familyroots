"""Marriage ORM model — global edge linking two persons."""

import uuid
from datetime import date

from sqlalchemy import Date, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from app.models.base import Base, TimestampMixin


class Marriage(TimestampMixin, Base):
    __tablename__ = "marriages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    person1_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="CASCADE"),
        index=True,
    )
    person2_id: Mapped[uuid.UUID] = mapped_column(
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

    marriage_date: Mapped[date | None] = mapped_column(Date, default=None)
    divorce_date: Mapped[date | None] = mapped_column(Date, default=None)
    marriage_place: Mapped[str | None] = mapped_column(
        String(255), default=None
    )
    status: Mapped[str] = mapped_column(
        String(20), default="married"
    )  # married, divorced, widowed, separated
    spouse_order: Mapped[int | None] = mapped_column(
        SmallInteger, default=None
    )  # vợ cả=1, vợ hai=2...

    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    # ── ORM Relationships ─────────────────────────────────────
    person1 = relationship(
        "Person",
        foreign_keys=[person1_id],
        back_populates="marriages_as_person1",
    )
    person2 = relationship(
        "Person",
        foreign_keys=[person2_id],
        back_populates="marriages_as_person2",
    )
    managing_clan = relationship("Clan")
