"""Domain events for the Branch bounded context.

Each event inherits from ``AuditableEvent`` so the ``AuditLogHandler``
automatically creates an ``AuditLog`` row without manual boilerplate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.shared.events import AuditableEvent


@dataclass(frozen=True)
class BranchCreated(AuditableEvent):
    """Emitted when a new branch is added to a clan."""

    branch_id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = ""

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "branch.create")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "branch")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.branch_id)


@dataclass(frozen=True)
class BranchUpdated(AuditableEvent):
    """Emitted when a branch is modified."""

    branch_id: uuid.UUID = field(default_factory=uuid.uuid4)
    changes: dict[str, Any] = field(default_factory=dict)
    old_values: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "branch.update")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "branch")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.branch_id)
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
class BranchDeleted(AuditableEvent):
    """Emitted when a branch is deleted."""

    branch_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "branch.delete")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "branch")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.branch_id)
