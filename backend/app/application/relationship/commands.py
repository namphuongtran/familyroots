"""Command DTOs for the Relationship use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from app.domain.shared.value_objects import ActorInfo

# ── Marriage Commands ────────────────────────────────────────────


@dataclass(frozen=True)
class CreateMarriage:
    person1_id: uuid.UUID
    person2_id: uuid.UUID
    clan_id: uuid.UUID
    actor: ActorInfo
    marriage_date: date | None = None
    divorce_date: date | None = None
    marriage_place: str | None = None
    status: str = "married"
    spouse_order: int | None = None
    notes: str | None = None


@dataclass(frozen=True)
class UpdateMarriage:
    marriage_id: uuid.UUID
    clan_id: uuid.UUID
    actor: ActorInfo
    changes: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DeleteMarriage:
    marriage_id: uuid.UUID
    clan_id: uuid.UUID
    actor: ActorInfo


# ── ParentChild Commands ─────────────────────────────────────────


@dataclass(frozen=True)
class CreateParentChild:
    parent_id: uuid.UUID
    child_id: uuid.UUID
    clan_id: uuid.UUID
    actor: ActorInfo
    relationship_type: str = "biological"
    birth_order: int | None = None
    notes: str | None = None


@dataclass(frozen=True)
class UpdateParentChild:
    link_id: uuid.UUID
    clan_id: uuid.UUID
    actor: ActorInfo
    changes: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DeleteParentChild:
    link_id: uuid.UUID
    clan_id: uuid.UUID
    actor: ActorInfo
