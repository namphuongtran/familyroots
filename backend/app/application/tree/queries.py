"""Query DTOs for the Tree use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class GetFullTree:
    clan_id: uuid.UUID
    root_person_id: uuid.UUID | None = None
    max_generations: int = 10


@dataclass(frozen=True)
class GetSubtree:
    person_id: uuid.UUID
    clan_id: uuid.UUID
    max_generations: int = 5


@dataclass(frozen=True)
class GetAncestors:
    person_id: uuid.UUID
    clan_id: uuid.UUID


@dataclass(frozen=True)
class FindPath:
    from_id: uuid.UUID
    to_id: uuid.UUID
    clan_id: uuid.UUID


@dataclass(frozen=True)
class GetFocusView:
    person_id: uuid.UUID
    clan_id: uuid.UUID
    ancestor_depth: int = 50
    descendant_depth: int = 2
