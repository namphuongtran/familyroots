"""ParentChild ORM model — global edge linking parent to child."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from app.models.base import Base, TimestampMixin


class ParentChild(TimestampMixin, Base):
    __tablename__ = "parent_child"
    # Edge-uniqueness is enforced by the partial, clan-scoped unique index
    # `idx_parent_child_unique_edge` (migrations 006/007/022), NOT a table constraint:
    # it must exclude soft-deleted rows and key on created_by_clan_id. As of 022 the
    # index keys on (created_by_clan_id, parent_id, child_id) ONLY — relationship_type
    # was dropped from the key, so at most one live edge is allowed per (clan, parent,
    # child) regardless of relationship_type (the app forbids a second live link on
    # the same pair even under a different type). Declaring a plain UniqueConstraint
    # here would (a) not match the DB and (b) make autogenerate try to recreate a
    # non-partial, non-clan-scoped constraint — reintroducing the soft-delete
    # re-create bug. So only the self-edge CheckConstraint lives here.
    # The bio-cap (max 2 live biological parents) and acyclicity invariants are
    # enforced by the `parent_child_integrity_guard` AFTER trigger (ADR-023); as of
    # 022 (ADR-025) that trigger opens with a per-clan pg_advisory_xact_lock so all
    # live-edge writes within a clan serialize, closing the disjoint-endpoint race
    # that per-person FOR UPDATE locks alone could not.
    __table_args__ = (CheckConstraint("parent_id != child_id", name="parent_child_no_self"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    parent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="RESTRICT"),
        index=True,
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="RESTRICT"),
        index=True,
    )

    # Clan that created/manages this record (for write RLS)
    created_by_clan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clans.id", ondelete="RESTRICT"),
        index=True,
    )

    # biological, adopted, step, foster
    relationship_type: Mapped[str] = mapped_column(String(20), default="biological")

    # Birth order among siblings under same parent (con cả=1, con thứ=2...)
    birth_order: Mapped[int | None] = mapped_column(SmallInteger, default=None)

    # Optimistic concurrency (ADR-017): bumped by every repository UPDATE;
    # PATCH requests must present the matching expected_version.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)

    # ── Soft delete ───────────────────────────────────────────
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)

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
