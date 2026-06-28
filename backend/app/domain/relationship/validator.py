"""Domain-level relationship validator.

Business rules that were previously in ``services/relationship_validator.py``
are rewritten here with domain-style exceptions. The actual DB queries are
delegated to the repository protocol so this validator stays infrastructure-free.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Protocol

from app.domain.shared.exceptions import (
    BusinessRuleViolation,
    ConflictError,
    EntityNotFoundError,
)


class RelationshipQueryPort(Protocol):
    """Minimal query port for relationship validation — implemented
    by the infrastructure repository."""

    async def count_bio_parents(self, child_id: uuid.UUID) -> int: ...
    async def has_active_marriage(self, person1_id: uuid.UUID, person2_id: uuid.UUID) -> bool: ...
    async def has_parent_child_link(self, parent_id: uuid.UUID, child_id: uuid.UUID) -> bool: ...
    async def is_ancestor(
        self, descendant_id: uuid.UUID, ancestor_id: uuid.UUID, clan_id: uuid.UUID
    ) -> bool: ...
    async def get_birth_dates(
        self, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, date | None]: ...
    async def persons_in_clan(
        self, person_ids: list[uuid.UUID], clan_id: uuid.UUID
    ) -> set[uuid.UUID]: ...


class RelationshipDomainValidator:
    """Pure-domain validation rules for relationships."""

    def __init__(self, query_port: RelationshipQueryPort) -> None:
        self._q = query_port

    async def ensure_persons_in_clan(self, person_ids: list[uuid.UUID], clan_id: uuid.UUID) -> None:
        """Every referenced person must be a member of the acting clan.

        Persons are global (M:N via clan_memberships); without this check a clan
        could create an edge referencing another clan's person and then read that
        person's data through the edge. Missing persons are reported as not-found
        (a person outside your clan is invisible to you) rather than forbidden, so
        the response does not leak whether the UUID exists in another clan.
        """
        present = await self._q.persons_in_clan(person_ids, clan_id)
        missing = set(person_ids) - present
        if missing:
            raise EntityNotFoundError(
                "person_not_found",
                detail={"person_ids": sorted(str(pid) for pid in missing)},
            )

    async def validate_parent_child(
        self,
        parent_id: uuid.UUID,
        child_id: uuid.UUID,
        relationship_type: str,
        clan_id: uuid.UUID,
    ) -> dict[str, object] | None:
        """Validate parent-child rules. Returns warning dict or None."""
        # Rule: no self-referencing
        if parent_id == child_id:
            raise BusinessRuleViolation("self_parent_not_allowed")

        # Rule: max 2 biological parents
        if relationship_type == "biological":
            bio_count = await self._q.count_bio_parents(child_id)
            if bio_count >= 2:
                raise ConflictError("relationship.too_many_biological_parents")

        # Rule: age gap check
        dates = await self._q.get_birth_dates([parent_id, child_id])
        parent_bd = dates.get(parent_id)
        child_bd = dates.get(child_id)
        if parent_bd and child_bd:
            age_gap = (child_bd - parent_bd).days / 365.25
            if age_gap < 12:
                raise BusinessRuleViolation(
                    "relationship.parent_too_young",
                    detail={"min_age_gap": 12, "actual": round(age_gap, 1)},
                )
            if age_gap > 80:
                return {"warning": f"Unusual age gap: {round(age_gap, 1)} years"}

        # Rule: cycle detection
        if await self._q.is_ancestor(parent_id, child_id, clan_id):
            raise BusinessRuleViolation("relationship.creates_cycle")

        return None

    async def check_duplicate_parent_child(self, parent_id: uuid.UUID, child_id: uuid.UUID) -> None:
        if await self._q.has_parent_child_link(parent_id, child_id):
            raise ConflictError("relationship.duplicate_parent_child")

    async def check_duplicate_marriage(self, person1_id: uuid.UUID, person2_id: uuid.UUID) -> None:
        if await self._q.has_active_marriage(person1_id, person2_id):
            raise ConflictError("relationship.duplicate_marriage")
