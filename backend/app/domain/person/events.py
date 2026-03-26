"""Domain events for the Person bounded context.

Each event inherits from ``AuditableEvent`` so the ``AuditLogHandler``
automatically creates an ``AuditLog`` row without manual boilerplate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.shared.events import AuditableEvent


@dataclass(frozen=True)
class PersonCreated(AuditableEvent):
    """Emitted when a new person is added to the system."""

    person_id: uuid.UUID = field(default_factory=uuid.uuid4)
    full_name: str = ""

    def __post_init__(self) -> None:
        # Frozen dataclass — use object.__setattr__ for computed fields
        if not self.action:
            object.__setattr__(self, "action", "person.create")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "person")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.person_id)


@dataclass(frozen=True)
class PersonUpdated(AuditableEvent):
    """Emitted when a person's details are modified."""

    person_id: uuid.UUID = field(default_factory=uuid.uuid4)
    changes: dict[str, Any] = field(default_factory=dict)
    old_values: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "person.update")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "person")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.person_id)
        if self.new_value is None and self.changes:
            # Serialize changes for audit log storage
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
class PersonDeleted(AuditableEvent):
    """Emitted when a person is soft-deleted."""

    person_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "person.delete")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "person")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.person_id)


@dataclass(frozen=True)
class PersonRestored(AuditableEvent):
    """Emitted when a soft-deleted person is restored."""

    person_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "person.restore")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "person")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.person_id)
