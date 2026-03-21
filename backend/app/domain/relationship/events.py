"""Domain events for the Relationship bounded context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.shared.events import AuditableEvent


# ── Marriage events ──────────────────────────────────────────────


@dataclass(frozen=True)
class MarriageCreated(AuditableEvent):
    marriage_id: uuid.UUID = field(default_factory=uuid.uuid4)
    person1_id: uuid.UUID = field(default_factory=uuid.uuid4)
    person2_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "marriage.create")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "marriage")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.marriage_id)


@dataclass(frozen=True)
class MarriageUpdated(AuditableEvent):
    marriage_id: uuid.UUID = field(default_factory=uuid.uuid4)
    changes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "marriage.update")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "marriage")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.marriage_id)


@dataclass(frozen=True)
class MarriageDeleted(AuditableEvent):
    marriage_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "marriage.delete")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "marriage")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.marriage_id)


# ── ParentChild events ───────────────────────────────────────────


@dataclass(frozen=True)
class ParentChildCreated(AuditableEvent):
    link_id: uuid.UUID = field(default_factory=uuid.uuid4)
    parent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    child_id: uuid.UUID = field(default_factory=uuid.uuid4)
    relationship_type: str = "biological"

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "parent_child.create")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "parent_child")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.link_id)


@dataclass(frozen=True)
class ParentChildUpdated(AuditableEvent):
    link_id: uuid.UUID = field(default_factory=uuid.uuid4)
    changes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "parent_child.update")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "parent_child")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.link_id)


@dataclass(frozen=True)
class ParentChildDeleted(AuditableEvent):
    link_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "parent_child.delete")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "parent_child")
        if self.resource_id is None:
            object.__setattr__(self, "resource_id", self.link_id)
