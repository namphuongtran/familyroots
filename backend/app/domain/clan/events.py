"""Domain events for the Clan bounded context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.shared.events import AuditableEvent


@dataclass(frozen=True)
class ClanUpdated(AuditableEvent):
    changes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "clan.update")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "clan")


@dataclass(frozen=True)
class ClanSuspended(AuditableEvent):
    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "clan.suspend")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "clan")


@dataclass(frozen=True)
class ClanReactivated(AuditableEvent):
    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "clan.reactivate")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "clan")


@dataclass(frozen=True)
class UserApproved(AuditableEvent):
    target_user_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "user.approve")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "user_clan_role")


@dataclass(frozen=True)
class UserRejected(AuditableEvent):
    target_user_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "user.reject")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "user_clan_role")


@dataclass(frozen=True)
class UserRoleChanged(AuditableEvent):
    target_user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    old_role: str = ""
    new_role: str = ""

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "user.change_role")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "user_clan_role")
        if self.old_value is None and self.old_role:
            object.__setattr__(self, "old_value", {"role": self.old_role})
        if self.new_value is None and self.new_role:
            object.__setattr__(self, "new_value", {"role": self.new_role})


@dataclass(frozen=True)
class UserRemoved(AuditableEvent):
    target_user_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "user.remove")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "user_clan_role")
