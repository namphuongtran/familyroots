"""Domain events for the clan invitation feature."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.shared.events import AuditableEvent


@dataclass(frozen=True)
class InvitationCreated(AuditableEvent):
    email: str = ""
    invited_role: str = ""

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "invitation.create")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "clan_invitation")


@dataclass(frozen=True)
class InvitationAccepted(AuditableEvent):
    email: str = ""

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "invitation.accept")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "clan_invitation")


@dataclass(frozen=True)
class InvitationRevoked(AuditableEvent):
    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "invitation.revoke")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "clan_invitation")
