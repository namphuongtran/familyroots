"""Command DTOs for the Clan use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.domain.shared.value_objects import ActorInfo


@dataclass(frozen=True)
class UpdateClan:
    clan_id: uuid.UUID
    actor: ActorInfo
    changes: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ApproveUser:
    clan_id: uuid.UUID
    target_user_id: uuid.UUID
    actor: ActorInfo


@dataclass(frozen=True)
class RejectUser:
    clan_id: uuid.UUID
    target_user_id: uuid.UUID
    actor: ActorInfo


@dataclass(frozen=True)
class ChangeUserRole:
    clan_id: uuid.UUID
    target_user_id: uuid.UUID
    new_role: str
    actor: ActorInfo


@dataclass(frozen=True)
class RemoveUser:
    clan_id: uuid.UUID
    target_user_id: uuid.UUID
    actor: ActorInfo


@dataclass(frozen=True)
class DesignateFounder:
    clan_id: uuid.UUID
    person_id: uuid.UUID
    actor: ActorInfo
