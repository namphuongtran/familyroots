"""Relationship domain entities — Marriage and ParentChild aggregates.

These are pure Python dataclasses, free of SQLAlchemy or FastAPI imports.
Each mutation method emits an AuditableEvent for automatic audit logging.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.domain.relationship.events import (
    MarriageCreated,
    MarriageDeleted,
    MarriageUpdated,
    ParentChildCreated,
    ParentChildDeleted,
    ParentChildUpdated,
)
from app.domain.shared.entity import AggregateRoot
from app.domain.shared.exceptions import BusinessRuleViolation
from app.domain.shared.value_objects import ActorInfo

# Fields a client may change via update(). Deliberately excludes the person ids,
# created_by_clan_id (edge ownership / isolation basis), and audit/soft-delete
# columns — those are set only by create()/soft_delete(), never a blind setattr.
_MARRIAGE_UPDATABLE_FIELDS = frozenset(
    {
        "marriage_date",
        "marriage_date_precision",
        "marriage_date_display",
        "divorce_date",
        "divorce_date_precision",
        "divorce_date_display",
        "marriage_place",
        "status",
        "spouse_order",
        "notes",
    }
)
_PARENT_CHILD_UPDATABLE_FIELDS = frozenset({"relationship_type", "birth_order", "notes"})


@dataclass
class Marriage(AggregateRoot):
    """Marriage aggregate — a bidirectional edge between two persons."""

    person1_id: uuid.UUID = field(default_factory=uuid.uuid4)
    person2_id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_by_clan_id: uuid.UUID = field(default_factory=uuid.uuid4)

    marriage_date: date | None = None
    marriage_date_precision: str = "exact"
    marriage_date_display: str | None = None
    divorce_date: date | None = None
    divorce_date_precision: str = "exact"
    divorce_date_display: str | None = None
    marriage_place: str | None = None
    status: str = "married"
    spouse_order: int | None = None
    notes: str | None = None

    # Audit
    created_by: uuid.UUID = field(default_factory=uuid.uuid4)
    updated_by: uuid.UUID | None = None

    # Soft delete
    is_deleted: bool = False
    deleted_at: datetime | None = None
    deleted_by: uuid.UUID | None = None

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.person1_id == self.person2_id:
            raise BusinessRuleViolation("self_marriage_not_allowed")

    @classmethod
    def create(
        cls,
        *,
        person1_id: uuid.UUID,
        person2_id: uuid.UUID,
        clan_id: uuid.UUID,
        actor: ActorInfo,
        **kwargs: Any,
    ) -> Marriage:
        marriage = cls(
            person1_id=person1_id,
            person2_id=person2_id,
            created_by_clan_id=clan_id,
            created_by=actor.user_id,
            **kwargs,
        )
        marriage.add_event(
            MarriageCreated(
                marriage_id=marriage.id,
                person1_id=person1_id,
                person2_id=person2_id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
            )
        )
        return marriage

    def update(self, changes: dict[str, object], actor: ActorInfo, clan_id: uuid.UUID) -> None:
        for field_name, new_value in changes.items():
            if field_name not in _MARRIAGE_UPDATABLE_FIELDS:
                raise BusinessRuleViolation("field_not_updatable", {"field": field_name})
            setattr(self, field_name, new_value)
        # Re-assert the construction invariant (defence in depth — person ids are
        # not updatable, so this cannot currently fail, but keeps the guard local
        # to every state change).
        if self.person1_id == self.person2_id:
            raise BusinessRuleViolation("self_marriage_not_allowed")
        self.updated_by = actor.user_id
        self.updated_at = datetime.now(UTC)

        self.add_event(
            MarriageUpdated(
                marriage_id=self.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                changes=changes,
            )
        )

    def soft_delete(self, actor: ActorInfo, clan_id: uuid.UUID) -> None:
        self.is_deleted = True
        self.deleted_at = datetime.now(UTC)
        self.deleted_by = actor.user_id

        self.add_event(
            MarriageDeleted(
                marriage_id=self.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
            )
        )


@dataclass
class ParentChild(AggregateRoot):
    """Parent-child aggregate — a directed edge from parent to child."""

    parent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    child_id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_by_clan_id: uuid.UUID = field(default_factory=uuid.uuid4)

    relationship_type: str = "biological"
    birth_order: int | None = None
    notes: str | None = None

    # Audit
    created_by: uuid.UUID = field(default_factory=uuid.uuid4)
    updated_by: uuid.UUID | None = None

    # Soft delete
    is_deleted: bool = False
    deleted_at: datetime | None = None
    deleted_by: uuid.UUID | None = None

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.parent_id == self.child_id:
            raise BusinessRuleViolation("self_parent_not_allowed")

    @classmethod
    def create(
        cls,
        *,
        parent_id: uuid.UUID,
        child_id: uuid.UUID,
        clan_id: uuid.UUID,
        actor: ActorInfo,
        **kwargs: Any,
    ) -> ParentChild:
        link = cls(
            parent_id=parent_id,
            child_id=child_id,
            created_by_clan_id=clan_id,
            created_by=actor.user_id,
            **kwargs,
        )
        link.add_event(
            ParentChildCreated(
                link_id=link.id,
                parent_id=parent_id,
                child_id=child_id,
                relationship_type=link.relationship_type,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
            )
        )
        return link

    def update(self, changes: dict[str, object], actor: ActorInfo, clan_id: uuid.UUID) -> None:
        for field_name, new_value in changes.items():
            if field_name not in _PARENT_CHILD_UPDATABLE_FIELDS:
                raise BusinessRuleViolation("field_not_updatable", {"field": field_name})
            setattr(self, field_name, new_value)
        if self.parent_id == self.child_id:
            raise BusinessRuleViolation("self_parent_not_allowed")
        self.updated_by = actor.user_id
        self.updated_at = datetime.now(UTC)

        self.add_event(
            ParentChildUpdated(
                link_id=self.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                changes=changes,
            )
        )

    def soft_delete(self, actor: ActorInfo, clan_id: uuid.UUID) -> None:
        self.is_deleted = True
        self.deleted_at = datetime.now(UTC)
        self.deleted_by = actor.user_id

        self.add_event(
            ParentChildDeleted(
                link_id=self.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
            )
        )
