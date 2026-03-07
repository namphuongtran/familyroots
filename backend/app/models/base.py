"""Declarative base and shared mixins for SQLAlchemy models."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class TimestampMixin:
    """Adds created_at and updated_at to any model."""

    created_at: Mapped[datetime] = mapped_column(  # noqa: F821
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(  # noqa: F821
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ClanScopedMixin(TimestampMixin):
    """Mixin for all tables that belong to a specific clan.

    Every query against these tables MUST include clan_id filter.
    RLS enforces this at DB level; application layer enforces it explicitly too.
    """

    clan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
