"""Domain events for the Event bounded context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.shared.events import AuditableEvent


@dataclass(frozen=True)
class EventCreated(AuditableEvent):
    """Emitted when a new event is created."""

    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    title: str = ""
    event_type: str = ""

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "event.create")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "event")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.event_id)


@dataclass(frozen=True)
class EventUpdated(AuditableEvent):
    """Emitted when an event is modified."""

    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    changes: dict[str, Any] = field(default_factory=dict)
    old_values: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "event.update")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "event")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.event_id)
        if self.new_value is None and self.changes:
            serializable = {
                k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                for k, v in self.changes.items()
            }
            object.__setattr__(self, "new_value", serializable)
        if self.old_value is None and self.old_values:
            serializable = {
                k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                for k, v in self.old_values.items()
            }
            object.__setattr__(self, "old_value", serializable)


@dataclass(frozen=True)
class EventDeleted(AuditableEvent):
    """Emitted when an event is deleted."""

    event_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "event.delete")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "event")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.event_id)


@dataclass(frozen=True)
class EventRestored(AuditableEvent):
    """Emitted when a soft-deleted event is restored (ADR-022)."""

    event_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "event.restore")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "event")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.event_id)
