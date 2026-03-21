"""Command and query DTOs for the Person use cases.

Commands represent intent to mutate state.
Queries represent intent to read data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from app.domain.shared.value_objects import ActorInfo

# ── Commands ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class CreatePerson:
    """Create a new person in a clan."""

    actor: ActorInfo
    clan_id: uuid.UUID

    full_name: str = ""
    gender: str = "unknown"
    birth_name: str | None = None
    courtesy_name: str | None = None
    posthumous_name: str | None = None
    alias_name: str | None = None

    birth_date: date | None = None
    birth_date_approx: bool = False
    death_date: date | None = None
    death_date_approx: bool = False
    lunar_birth_date: str | None = None
    lunar_death_date: str | None = None

    birth_place: str | None = None
    death_place: str | None = None
    burial_place: str | None = None
    tomb_location: str | None = None
    residence_place: str | None = None

    religion: str | None = None
    nationality: str = "VN"
    occupation: str | None = None
    education_level: str | None = None
    title_rank: str | None = None
    phone: str | None = None
    email: str | None = None

    biography: str | None = None
    avatar_url: str | None = None
    notes: str | None = None
    created_by_clan_id: uuid.UUID | None = None

    # Membership-specific
    membership_role: str = "blood"
    generation: int | None = None
    is_founder: bool = False
    branch_id: uuid.UUID | None = None


@dataclass(frozen=True)
class UpdatePerson:
    """Update an existing person's details."""

    person_id: uuid.UUID
    clan_id: uuid.UUID
    actor: ActorInfo
    changes: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DeletePerson:
    """Soft-delete a person."""

    person_id: uuid.UUID
    clan_id: uuid.UUID
    actor: ActorInfo


@dataclass(frozen=True)
class RestorePerson:
    """Restore a soft-deleted person."""

    person_id: uuid.UUID
    clan_id: uuid.UUID
    actor: ActorInfo


# ── Queries ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ListPersons:
    """List persons in a clan with filtering and pagination."""

    clan_id: uuid.UUID
    gender: str | None = None
    is_deleted: bool = False
    generation: int | None = None
    branch_id: uuid.UUID | None = None
    cursor: str | None = None
    limit: int = 50


@dataclass(frozen=True)
class SearchPersons:
    """Free-text search for persons in a clan."""

    clan_id: uuid.UUID
    query: str = ""
    limit: int = 10


@dataclass(frozen=True)
class GetPerson:
    """Get a single person by ID within a clan."""

    person_id: uuid.UUID
    clan_id: uuid.UUID


@dataclass(frozen=True)
class GetPersonTimeline:
    """Get a person's timeline (events, relationships, etc.)."""

    person_id: uuid.UUID
    clan_id: uuid.UUID
