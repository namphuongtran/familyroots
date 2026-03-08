"""Clan ORM model (public schema) — uses TimestampMixin only, NOT ClanScopedMixin."""

import uuid

from sqlalchemy import Boolean, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Clan(TimestampMixin, Base):
    __tablename__ = "clans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    origin_place: Mapped[str | None] = mapped_column(String(255), default=None)
    founded_year: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    avatar_url: Mapped[str | None] = mapped_column(String(500), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── Genealogy metadata ────────────────────────────────────
    motto: Mapped[str | None] = mapped_column(Text, default=None)
    ancestral_hall_location: Mapped[str | None] = mapped_column(
        String(500), default=None
    )  # nhà thờ tổ
    clan_rules: Mapped[str | None] = mapped_column(
        Text, default=None
    )  # gia huấn

    # ── ORM Relationships ─────────────────────────────────────
    origin_persons = relationship(
        "Person", back_populates="origin_clan", lazy="selectin"
    )
    clan_memberships = relationship(
        "ClanMembership", back_populates="clan", lazy="selectin"
    )
    user_roles = relationship(
        "UserClanRole", back_populates="clan", lazy="selectin"
    )
    settings = relationship(
        "ClanSettings", back_populates="clan", uselist=False, lazy="selectin"
    )
    branches = relationship(
        "Branch", back_populates="clan", lazy="selectin"
    )
