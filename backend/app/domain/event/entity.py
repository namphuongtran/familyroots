"""Event domain entity — pure Python, no framework dependencies.

The Event aggregate root encapsulates business rules for clan events:
type validation, field-level update control, and recurring event logic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from app.domain.event.events import EventCreated, EventDeleted, EventUpdated
from app.domain.shared.entity import AggregateRoot
from app.domain.shared.exceptions import BusinessRuleViolation
from app.domain.shared.value_objects import ActorInfo

_VALID_EVENT_TYPES = frozenset({
    "death_anniversary", "birthday", "wedding_anniversary", "clan_ceremony", "custom",
})

_UPDATABLE_FIELDS = frozenset({
    "event_type", "title", "description", "event_date",
    "is_lunar_calendar", "is_recurring", "notify_days_before",
})


@dataclass
class Event(AggregateRoot):
    """Event aggregate root.

    Represents a clan event such as a death anniversary, birthday, or ceremony.
    """

    # ── Identity ──────────────────────────────────────────────
    clan_id: uuid.UUID = field(default_factory=uuid.uuid4)
    person_id: uuid.UUID | None = None
    event_type: str = "custom"
    title: str = ""
    description: str | None = None

    # ── Date handling ─────────────────────────────────────────
    event_date: date = field(default_factory=date.today)
    is_lunar_calendar: bool = False
    is_recurring: bool = True
    notify_days_before: int = 7

    # ── Audit ─────────────────────────────────────────────────
    created_by: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # ── Domain methods ────────────────────────────────────────

    @classmethod
    def create(
        cls,
        *,
        clan_id: uuid.UUID,
        actor: ActorInfo,
        event_type: str,
        title: str,
        event_date: date,
        person_id: uuid.UUID | None = None,
        description: str | None = None,
        is_lunar_calendar: bool = False,
        is_recurring: bool = True,
        notify_days_before: int = 7,
    ) -> Event:
        """Factory method to create a new Event with validation."""
        if event_type not in _VALID_EVENT_TYPES:
            raise BusinessRuleViolation("invalid_event_type", {"event_type": event_type})

        event = cls(
            clan_id=clan_id,
            person_id=person_id,
            event_type=event_type,
            title=title,
            description=description,
            event_date=event_date,
            is_lunar_calendar=is_lunar_calendar,
            is_recurring=is_recurring,
            notify_days_before=notify_days_before,
            created_by=actor.user_id,
        )
        event.add_event(
            EventCreated(
                event_id=event.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                title=title,
                event_type=event_type,
            )
        )
        return event

    def update(self, changes: dict[str, object], actor: ActorInfo) -> None:
        """Apply a partial update with field whitelist enforcement."""
        old_values: dict[str, object] = {}
        for field_name, new_value in changes.items():
            if field_name not in _UPDATABLE_FIELDS:
                raise BusinessRuleViolation(
                    "field_not_updatable", {"field": field_name}
                )
            old_values[field_name] = getattr(self, field_name, None)
            setattr(self, field_name, new_value)

        # Validate event_type if it was changed
        if "event_type" in changes and self.event_type not in _VALID_EVENT_TYPES:
            raise BusinessRuleViolation(
                "invalid_event_type", {"event_type": self.event_type}
            )

        self.updated_at = datetime.now(UTC)
        self.add_event(
            EventUpdated(
                event_id=self.id,
                clan_id=self.clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                changes=changes,
                old_values=old_values,
            )
        )

    def delete(self, actor: ActorInfo) -> None:
        """Emit a deletion event."""
        self.add_event(
            EventDeleted(
                event_id=self.id,
                clan_id=self.clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
            )
        )
