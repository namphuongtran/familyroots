"""Event ORM model — death anniversaries, birthdays, clan ceremonies."""

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from app.models.base import Base, ClanScopedMixin


class Event(ClanScopedMixin, Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="CASCADE"),
        default=None,
    )

    event_type: Mapped[str] = mapped_column(String(30))  # 'death_anniversary','birthday',...
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    # Date handling for lunar/solar calendar
    event_date: Mapped[date] = mapped_column(Date)
    # HistoricalDate foundation: backfilled 'exact' by migration 012 (event_date is
    # NOT NULL, so precision is always 'exact' today).
    event_date_precision: Mapped[str] = mapped_column(String(10), default="exact")
    event_date_display: Mapped[str | None] = mapped_column(String(100), default=None)
    is_lunar_calendar: Mapped[bool] = mapped_column(Boolean, default=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_days_before: Mapped[int] = mapped_column(SmallInteger, default=7)

    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    # ORM relationships
    person = relationship("Person", back_populates="events")
