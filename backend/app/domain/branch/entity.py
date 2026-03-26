"""Branch domain entity — pure Python, no framework dependencies.

The Branch aggregate root encapsulates domain rules for clan branches
(chi/phái/nhánh): hierarchical parent validation, ordering, and
field-level update control. Each mutation emits a domain event for
automatic audit logging.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.branch.events import BranchCreated, BranchDeleted, BranchUpdated
from app.domain.shared.entity import AggregateRoot
from app.domain.shared.exceptions import BusinessRuleViolation
from app.domain.shared.value_objects import ActorInfo

_UPDATABLE_FIELDS = frozenset(
    {
        "name",
        "description",
        "founder_person_id",
        "parent_branch_id",
        "branch_order",
    }
)


@dataclass
class Branch(AggregateRoot):
    """Branch aggregate root.

    Represents a clan branch (chi/phái) in the genealogy system.
    Branches form a tree hierarchy via ``parent_branch_id``.
    """

    # ── Identity ──────────────────────────────────────────────
    clan_id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = ""
    description: str | None = None

    # ── Relationships ─────────────────────────────────────────
    founder_person_id: uuid.UUID | None = None
    parent_branch_id: uuid.UUID | None = None

    # ── Ordering ──────────────────────────────────────────────
    branch_order: int | None = None

    # ── Timestamps ────────────────────────────────────────────
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # ── Domain methods ────────────────────────────────────────

    @classmethod
    def create(
        cls,
        *,
        clan_id: uuid.UUID,
        name: str,
        actor: ActorInfo,
        description: str | None = None,
        founder_person_id: uuid.UUID | None = None,
        parent_branch_id: uuid.UUID | None = None,
        branch_order: int | None = None,
    ) -> Branch:
        """Factory method to create a new Branch with a creation event."""
        branch = cls(
            clan_id=clan_id,
            name=name,
            description=description,
            founder_person_id=founder_person_id,
            parent_branch_id=parent_branch_id,
            branch_order=branch_order,
        )
        branch.add_event(
            BranchCreated(
                branch_id=branch.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                name=name,
            )
        )
        return branch

    def update(self, changes: dict[str, object], actor: ActorInfo) -> None:
        """Apply a partial update with field whitelist enforcement."""
        old_values: dict[str, object] = {}
        for field_name, new_value in changes.items():
            if field_name not in _UPDATABLE_FIELDS:
                raise BusinessRuleViolation("field_not_updatable", {"field": field_name})
            old_values[field_name] = getattr(self, field_name, None)
            setattr(self, field_name, new_value)

        # Guard: a branch cannot be its own parent
        if self.parent_branch_id == self.id:
            raise BusinessRuleViolation("branch_cannot_be_own_parent")

        self.updated_at = datetime.now(UTC)
        self.add_event(
            BranchUpdated(
                branch_id=self.id,
                clan_id=self.clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                changes=changes,
                old_values=old_values,
            )
        )

    def delete(self, actor: ActorInfo) -> None:
        """Emit a deletion event (hard delete is handled by repository)."""
        self.add_event(
            BranchDeleted(
                branch_id=self.id,
                clan_id=self.clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
            )
        )
