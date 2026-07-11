"""Person ORM model — global entity independent of any clan."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from app.models.base import Base, TimestampMixin


class Person(TimestampMixin, Base):
    __tablename__ = "persons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Origin clan (nullable — may not belong to any clan in the system)
    created_by_clan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clans.id", ondelete="SET NULL"),
        default=None,
        index=True,
    )

    # ── Identity ──────────────────────────────────────────────
    full_name: Mapped[str] = mapped_column(String(255))
    birth_name: Mapped[str | None] = mapped_column(String(255), default=None)
    courtesy_name: Mapped[str | None] = mapped_column(String(255), default=None)  # tên tự / tên chữ
    posthumous_name: Mapped[str | None] = mapped_column(
        String(255), default=None
    )  # tên huý / tên thụy
    alias_name: Mapped[str | None] = mapped_column(String(255), default=None)  # biệt danh
    gender: Mapped[str] = mapped_column(String(20), default="unknown")

    # ── Dates (solar — canonical for sorting/computing) ───────
    birth_date: Mapped[date | None] = mapped_column(Date, default=None)
    death_date: Mapped[date | None] = mapped_column(Date, default=None)

    # ── Date precision/display (HistoricalDate — canonical source; the legacy
    # boolean "estimated date" flags were backfilled into these by migration 012
    # and dropped by migration 014) ────────────────────────────
    birth_date_precision: Mapped[str] = mapped_column(String(10), default="exact")
    birth_date_display: Mapped[str | None] = mapped_column(String(100), default=None)
    death_date_precision: Mapped[str] = mapped_column(String(10), default="exact")
    death_date_display: Mapped[str | None] = mapped_column(String(100), default=None)

    # ── Dates (lunar — display only, e.g. "15/08 Nhâm Tý") ──
    lunar_birth_date: Mapped[str | None] = mapped_column(String(30), default=None)
    lunar_death_date: Mapped[str | None] = mapped_column(String(30), default=None)

    # ── Places ────────────────────────────────────────────────
    birth_place: Mapped[str | None] = mapped_column(String(255), default=None)
    death_place: Mapped[str | None] = mapped_column(String(255), default=None)
    burial_place: Mapped[str | None] = mapped_column(String(255), default=None)  # nơi an táng
    tomb_location: Mapped[str | None] = mapped_column(String(500), default=None)  # phần mộ hiện tại
    residence_place: Mapped[str | None] = mapped_column(String(255), default=None)

    # ── Personal info ─────────────────────────────────────────
    religion: Mapped[str | None] = mapped_column(String(100), default=None)
    # Nullable in the DB (baseline migration); the "VN" default applies on insert but
    # the column permits NULL, so the ORM type must be Optional to match — otherwise
    # autogenerate sees a modify_nullable drift.
    nationality: Mapped[str | None] = mapped_column(String(100), default="VN")
    occupation: Mapped[str | None] = mapped_column(String(255), default=None)
    education_level: Mapped[str | None] = mapped_column(String(255), default=None)
    title_rank: Mapped[str | None] = mapped_column(String(255), default=None)  # chức danh, phẩm hàm
    phone: Mapped[str | None] = mapped_column(String(50), default=None)
    email: Mapped[str | None] = mapped_column(String(255), default=None)

    # ── Content ───────────────────────────────────────────────
    biography: Mapped[str | None] = mapped_column(Text, default=None)
    avatar_url: Mapped[str | None] = mapped_column(String(500), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    # ── Soft delete ───────────────────────────────────────────
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)

    # ── Audit ─────────────────────────────────────────────────
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)

    # ── ORM Relationships ─────────────────────────────────────
    origin_clan = relationship("Clan", back_populates="origin_persons")
    user_profile = relationship("UserProfile", back_populates="person", uselist=False)
    clan_memberships = relationship("ClanMembership", back_populates="person", lazy="noload")
    documents = relationship("Document", back_populates="person", lazy="noload")
    events = relationship("Event", back_populates="person", lazy="noload")
    marriages_as_person1 = relationship(
        "Marriage",
        foreign_keys="Marriage.person1_id",
        back_populates="person1",
    )
    marriages_as_person2 = relationship(
        "Marriage",
        foreign_keys="Marriage.person2_id",
        back_populates="person2",
    )
    parent_links = relationship(
        "ParentChild",
        foreign_keys="ParentChild.parent_id",
        back_populates="parent",
    )
    child_links = relationship(
        "ParentChild",
        foreign_keys="ParentChild.child_id",
        back_populates="child",
    )
