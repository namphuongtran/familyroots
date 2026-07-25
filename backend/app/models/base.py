"""Declarative base and shared mixins for SQLAlchemy models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Standard Alembic naming convention so future autogenerate runs produce stable,
# predictable constraint/index names. Constraints that are explicitly named in
# models or the baseline migration keep their given names.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """Adds created_at and updated_at to any model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ClanScopedMixin(TimestampMixin):
    """Mixin for all tables that belong to a specific clan.

    Every query against these tables MUST include a clan_id filter. Clan
    isolation is enforced in the application layer (the repository contract) as the
    PRIMARY guarantee; RLS layer-2 (SP-3, ADR-008) is defense-in-depth behind it and is
    now active for some of these tables (documents, events, branches) — see
    ``app/core/rls.py``.
    """

    clan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
