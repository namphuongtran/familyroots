"""Branch ORM model — chi/phái/nhánh within a clan."""

import uuid

from sqlalchemy import SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey

from app.models.base import Base, TimestampMixin


class Branch(TimestampMixin, Base):
    __tablename__ = "branches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    clan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255))  # "Chi Hai", "Phái Bắc"
    description: Mapped[str | None] = mapped_column(Text, default=None)

    # The person who founded this branch
    founder_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="SET NULL"),
        default=None,
    )

    # Self-referential: parent branch (tree of branches)
    parent_branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="SET NULL"),
        default=None,
    )

    # Display order among sibling branches
    branch_order: Mapped[int | None] = mapped_column(SmallInteger, default=None)

    # ── ORM Relationships ─────────────────────────────────────
    clan = relationship("Clan", back_populates="branches")
    founder = relationship("Person", foreign_keys=[founder_person_id])
    parent_branch = relationship(
        "Branch", remote_side=[id], back_populates="child_branches"
    )
    child_branches = relationship(
        "Branch", back_populates="parent_branch", lazy="selectin"
    )
    members = relationship("ClanMembership", back_populates="branch")
