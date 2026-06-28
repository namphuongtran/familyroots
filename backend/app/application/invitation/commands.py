"""Command DTOs for the invitation use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.domain.shared.value_objects import ActorInfo


@dataclass(frozen=True)
class CreateInvitation:
    clan_id: uuid.UUID
    email: str
    role: str
    actor: ActorInfo


@dataclass(frozen=True)
class AcceptInvitation:
    token: str
    user_id: uuid.UUID
    user_email: str
    user_full_name: str


@dataclass(frozen=True)
class RevokeInvitation:
    clan_id: uuid.UUID
    invitation_id: uuid.UUID
    actor: ActorInfo
