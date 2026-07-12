"""Person domain entity — pure Python, no framework dependencies.

The Person aggregate root encapsulates all business rules related to
person management: creating, updating, soft-deleting, and restoring.
Each mutation emits a domain event for automatic audit logging.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.domain.person.events import (
    PersonCreated,
    PersonDeleted,
    PersonRestored,
    PersonUpdated,
)
from app.domain.shared.entity import AggregateRoot
from app.domain.shared.exceptions import BusinessRuleViolation
from app.domain.shared.value_objects import ActorInfo

# Profile fields a client may change via update() (mirrors the PersonUpdate schema).
# Excludes created_by_clan_id (origin/isolation), soft-delete, and audit columns —
# those are set only by create()/soft_delete()/restore(), never a blind setattr.
_UPDATABLE_FIELDS = frozenset(
    {
        "full_name",
        "birth_name",
        "courtesy_name",
        "posthumous_name",
        "alias_name",
        "gender",
        "birth_date",
        "birth_date_precision",
        "birth_date_display",
        "death_date",
        "death_date_precision",
        "death_date_display",
        "lunar_birth_date",
        "lunar_death_date",
        "birth_place",
        "death_place",
        "burial_place",
        "tomb_location",
        "residence_place",
        "religion",
        "nationality",
        "occupation",
        "education_level",
        "title_rank",
        "phone",
        "email",
        "biography",
        "avatar_url",
        "notes",
    }
)


@dataclass
class Person(AggregateRoot):
    """Person aggregate root.

    Represents an individual in the genealogy system. A Person may belong
    to multiple clans via ClanMembership links, but the entity itself is
    clan-independent.
    """

    # ── Identity ──────────────────────────────────────────────
    full_name: str = ""
    birth_name: str | None = None
    courtesy_name: str | None = None
    posthumous_name: str | None = None
    alias_name: str | None = None
    gender: str = "unknown"

    # ── Dates (solar) ─────────────────────────────────────────
    birth_date: date | None = None
    birth_date_precision: str = "exact"
    birth_date_display: str | None = None
    death_date: date | None = None
    death_date_precision: str = "exact"
    death_date_display: str | None = None

    # ── Dates (lunar — display only) ──────────────────────────
    lunar_birth_date: str | None = None
    lunar_death_date: str | None = None

    # ── Places ────────────────────────────────────────────────
    birth_place: str | None = None
    death_place: str | None = None
    burial_place: str | None = None
    tomb_location: str | None = None
    residence_place: str | None = None

    # ── Personal info ─────────────────────────────────────────
    religion: str | None = None
    nationality: str = "VN"
    occupation: str | None = None
    education_level: str | None = None
    title_rank: str | None = None
    phone: str | None = None
    email: str | None = None

    # ── Content ───────────────────────────────────────────────
    biography: str | None = None
    avatar_url: str | None = None
    notes: str | None = None

    # ── Origin ────────────────────────────────────────────────
    created_by_clan_id: uuid.UUID | None = None

    # ── Soft delete ───────────────────────────────────────────
    is_deleted: bool = False
    deleted_at: datetime | None = None
    deleted_by: uuid.UUID | None = None

    # ── Audit ─────────────────────────────────────────────────
    created_by: uuid.UUID = field(default_factory=uuid.uuid4)
    updated_by: uuid.UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Optimistic concurrency (ADR-017). Not client-updatable; the repository
    # bumps it on every successful UPDATE.
    version: int = 1

    # ── Domain methods ────────────────────────────────────────

    @classmethod
    def create(
        cls,
        *,
        full_name: str,
        actor: ActorInfo,
        clan_id: uuid.UUID,
        **kwargs: Any,
    ) -> Person:
        """Factory method to create a new Person with a creation event."""
        person = cls(
            full_name=full_name,
            created_by=actor.user_id,
            **kwargs,
        )
        person._validate_dates()
        person.add_event(
            PersonCreated(
                person_id=person.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                full_name=full_name,
            )
        )
        return person

    def update(self, changes: dict[str, object], actor: ActorInfo, clan_id: uuid.UUID) -> None:
        """Apply a partial update and emit a PersonUpdated event.

        ``changes`` is a dict of field name → new value (only non-None
        values from the Pydantic update schema).
        """
        old_values: dict[str, object] = {}
        for field_name, new_value in changes.items():
            if field_name not in _UPDATABLE_FIELDS:
                raise BusinessRuleViolation("field_not_updatable", {"field": field_name})
            old_values[field_name] = getattr(self, field_name, None)
            setattr(self, field_name, new_value)

        self._validate_dates()
        self.updated_by = actor.user_id
        self.updated_at = datetime.now(UTC)

        self.add_event(
            PersonUpdated(
                person_id=self.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                changes=changes,
                old_values=old_values,
            )
        )

    def _validate_dates(self) -> None:
        """Reject an impossible lifespan (death before birth).

        Called from the write paths (create/update) ONLY — deliberately NOT in
        __post_init__, because the persistence mapper reconstructs Person from every DB
        row and must not raise on pre-existing rows that predate this rule. This is the
        single source of truth for the cross-field rule (the API schema does not
        duplicate it), so it also covers partial PATCH updates. Date precision is
        intentionally ignored — death before birth is impossible regardless of how
        precisely either date is known.
        """
        if self.birth_date and self.death_date and self.death_date < self.birth_date:
            raise BusinessRuleViolation(
                "person.death_before_birth",
                detail={"birth_date": str(self.birth_date), "death_date": str(self.death_date)},
            )

    def soft_delete(self, actor: ActorInfo, clan_id: uuid.UUID) -> None:
        """Mark the person as soft-deleted."""
        self.is_deleted = True
        self.deleted_at = datetime.now(UTC)
        self.deleted_by = actor.user_id

        self.add_event(
            PersonDeleted(
                person_id=self.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
            )
        )

    def restore(self, actor: ActorInfo, clan_id: uuid.UUID) -> None:
        """Restore a soft-deleted person."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None

        self.add_event(
            PersonRestored(
                person_id=self.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
            )
        )
