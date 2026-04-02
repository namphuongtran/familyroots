"""Repository protocol for the Person bounded context.

Defines the abstract persistence contract. The SQLAlchemy implementation
lives in ``app.infrastructure.persistence.person_repository``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.domain.person.entity import Person


@dataclass(frozen=True)
class PersonFilters:
    """Filter criteria for listing persons in a clan."""

    gender: str | None = None
    is_deleted: bool = False
    generation: int | None = None
    branch_id: uuid.UUID | None = None
    search_query: str | None = None


@dataclass(frozen=True)
class PersonSearchResult:
    """Lightweight result for person search (autocomplete)."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    full_name: str = ""
    birth_name: str | None = None
    birth_date: date | None = None
    gender: str = "unknown"
    avatar_url: str | None = None
    generation: int | None = None
    membership_role: str | None = None
    is_founder: bool | None = None


class PersonRepository(Protocol):
    """Abstract persistence contract for Person entities."""

    async def get_by_id(self, person_id: uuid.UUID) -> Person | None:
        """Fetch a person by their global ID (not clan-scoped)."""
        ...

    async def get_in_clan(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> Person | None:
        """Fetch a person only if they belong to the given clan."""
        ...

    async def list_in_clan(
        self,
        clan_id: uuid.UUID,
        filters: PersonFilters,
        cursor: str | None = None,
        limit: int = 50,
    ) -> list[Person]:
        """List persons in a clan with optional filters and cursor pagination."""
        ...

    async def search(
        self,
        clan_id: uuid.UUID,
        query: str,
        limit: int = 10,
    ) -> list[PersonSearchResult]:
        """Full-text / trigram search for persons in a clan."""
        ...

    async def save(self, person: Person) -> None:
        """Insert or update a Person entity."""
        ...

    async def save_with_membership(
        self,
        person: Person,
        clan_id: uuid.UUID,
        role: str = "blood",
        generation: int | None = None,
        is_founder: bool = False,
        branch_id: uuid.UUID | None = None,
    ) -> None:
        """Save a Person and create its ClanMembership link atomically."""
        ...

    async def count_in_clan(self, clan_id: uuid.UUID, is_deleted: bool = False) -> int:
        """Count persons in a clan (for pagination metadata)."""
        ...

    async def get_stats_for_persons(
        self, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, int]]:
        """Get spouse and child counts for a list of persons."""
        ...
