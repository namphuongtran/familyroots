"""Member ORM model — uses ClanScopedMixin for clan_id isolation."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, ClanScopedMixin


class Member(ClanScopedMixin, Base):
    __tablename__ = "members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identity
    full_name: Mapped[str] = mapped_column(String(255))
    birth_name: Mapped[str | None] = mapped_column(String(255), default=None)
    courtesy_name: Mapped[str | None] = mapped_column(String(255), default=None)
    gender: Mapped[str] = mapped_column(String(20), default="unknown")

    # Dates
    birth_date: Mapped[date | None] = mapped_column(Date, default=None)
    birth_date_approx: Mapped[bool] = mapped_column(Boolean, default=False)
    death_date: Mapped[date | None] = mapped_column(Date, default=None)
    death_date_approx: Mapped[bool] = mapped_column(Boolean, default=False)

    # Places
    birth_place: Mapped[str | None] = mapped_column(String(255), default=None)
    death_place: Mapped[str | None] = mapped_column(String(255), default=None)
    residence_place: Mapped[str | None] = mapped_column(String(255), default=None)

    # Genealogy metadata
    generation: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    is_clan_founder: Mapped[bool] = mapped_column(Boolean, default=False)
    is_clan_member: Mapped[bool] = mapped_column(Boolean, default=True)

    # Content
    biography: Mapped[str | None] = mapped_column(Text, default=None)
    avatar_url: Mapped[str | None] = mapped_column(String(500), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)

    # Audit
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)

    # ORM relationships
    clan = relationship("Clan", back_populates="members")
    documents = relationship("Document", back_populates="member", lazy="selectin")
    events = relationship("Event", back_populates="member", lazy="selectin")
    user_account = relationship("UserClanRole", back_populates="member", uselist=False)
    relationships_as_member = relationship(
        "Relationship", foreign_keys="Relationship.member_id", back_populates="member"
    )
    relationships_as_related = relationship(
        "Relationship", foreign_keys="Relationship.related_id", back_populates="related"
    )
