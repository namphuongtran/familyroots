"""Domain events for the ChangeRequest bounded context.

Each event inherits from ``AuditableEvent`` so the ``AuditLogHandler`` writes an
``AuditLog`` row inside the same transaction (ADR-014). Approving a person change
request therefore produces TWO audit rows in one transaction: the
``change_request.approve`` row below and the ordinary ``person.update`` row emitted
by the Person aggregate — the approval and the edit it caused are both attributable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.shared.events import AuditableEvent

_RESOURCE_TYPE = "change_request"


@dataclass(frozen=True)
class ChangeRequestSubmitted(AuditableEvent):
    """Emitted when a clan member proposes a change."""

    change_request_id: uuid.UUID = field(default_factory=uuid.uuid4)
    target_resource_type: str = ""
    target_resource_id: uuid.UUID | None = None
    fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "change_request.submit")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", _RESOURCE_TYPE)
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.change_request_id)
        if self.new_value is None:
            object.__setattr__(
                self,
                "new_value",
                {
                    "target_resource_type": self.target_resource_type,
                    "target_resource_id": str(self.target_resource_id)
                    if self.target_resource_id
                    else None,
                    "fields": list(self.fields),
                },
            )


@dataclass(frozen=True)
class ChangeRequestApproved(AuditableEvent):
    """Emitted when a reviewer approves a change request and it is applied."""

    change_request_id: uuid.UUID = field(default_factory=uuid.uuid4)
    target_resource_type: str = ""
    target_resource_id: uuid.UUID | None = None
    changes: dict[str, Any] = field(default_factory=dict)
    base_version: int = 1
    applied_version: int | None = None

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "change_request.approve")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", _RESOURCE_TYPE)
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.change_request_id)
        if self.new_value is None:
            object.__setattr__(
                self,
                "new_value",
                {
                    "target_resource_type": self.target_resource_type,
                    "target_resource_id": str(self.target_resource_id)
                    if self.target_resource_id
                    else None,
                    "changes": self.changes,
                    # The version the proposal was written against vs the version the
                    # target actually reached — the merge audit trail (ADR-037).
                    "base_version": self.base_version,
                    "applied_version": self.applied_version,
                },
            )


@dataclass(frozen=True)
class ChangeRequestRejected(AuditableEvent):
    """Emitted when a reviewer rejects a change request. Nothing is applied."""

    change_request_id: uuid.UUID = field(default_factory=uuid.uuid4)
    target_resource_type: str = ""
    target_resource_id: uuid.UUID | None = None
    review_notes: str | None = None

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "change_request.reject")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", _RESOURCE_TYPE)
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.change_request_id)
        if self.new_value is None:
            object.__setattr__(
                self,
                "new_value",
                {
                    "target_resource_type": self.target_resource_type,
                    "target_resource_id": str(self.target_resource_id)
                    if self.target_resource_id
                    else None,
                    "review_notes": self.review_notes,
                },
            )
