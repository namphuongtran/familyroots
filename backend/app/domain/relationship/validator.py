"""Domain-level relationship validator.

Business rules that were previously in ``services/relationship_validator.py``
are rewritten here with domain-style exceptions. The actual DB queries are
delegated to the repository protocol so this validator stays infrastructure-free.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.domain.shared.exceptions import (
    BusinessRuleViolation,
    ConflictError,
    EntityNotFoundError,
)


@dataclass(frozen=True)
class BirthDate:
    """A person's birth date plus its recorded precision.

    ``get_birth_dates`` must surface precision alongside the value: an age-gap
    computed from a 'circa'/'year'/'month'/'unknown' estimate cannot justify a
    hard business-rule block (ADR-011) the way an 'exact' date can.
    """

    value: date | None
    precision: str


class RelationshipQueryPort(Protocol):
    """Minimal query port for relationship validation — implemented
    by the infrastructure repository."""

    async def count_bio_parents(
        self,
        child_id: uuid.UUID,
        clan_id: uuid.UUID,
        exclude_link_id: uuid.UUID | None = None,
    ) -> int: ...
    async def has_active_marriage(
        self,
        person1_id: uuid.UUID,
        person2_id: uuid.UUID,
        clan_id: uuid.UUID,
        exclude_marriage_id: uuid.UUID | None = None,
    ) -> bool: ...
    async def has_parent_child_link(
        self, parent_id: uuid.UUID, child_id: uuid.UUID, clan_id: uuid.UUID
    ) -> bool: ...
    async def is_ancestor(
        self, descendant_id: uuid.UUID, ancestor_id: uuid.UUID, clan_id: uuid.UUID
    ) -> bool: ...
    async def get_birth_dates(self, person_ids: list[uuid.UUID]) -> dict[uuid.UUID, BirthDate]: ...
    async def persons_in_clan(
        self, person_ids: list[uuid.UUID], clan_id: uuid.UUID
    ) -> set[uuid.UUID]: ...
    async def has_spouse_order_conflict(
        self,
        person_a: uuid.UUID,
        person_b: uuid.UUID,
        spouse_order: int,
        clan_id: uuid.UUID,
        exclude_marriage_id: uuid.UUID | None = None,
    ) -> bool: ...


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
        *,
        exclude_link_id: uuid.UUID | None = None,
        check_cycle: bool = True,
    ) -> dict[str, object] | None:
        """Validate parent-child rules. Returns warning dict or None."""
        # Rule: no self-referencing
        if parent_id == child_id:
            raise BusinessRuleViolation("self_parent_not_allowed")

        dates = await self._q.get_birth_dates([parent_id, child_id])
        parent = dates.get(parent_id)
        child = dates.get(child_id)
        parent_bd = parent.value if parent else None
        child_bd = child.value if child else None
        both_exact = bool(
            parent and child and parent.precision == "exact" and child.precision == "exact"
        )
        age_gap = (child_bd - parent_bd).days / 365.25 if parent_bd and child_bd else None

        warning: str | None = None
        if relationship_type == "biological":
            # Rule: max 2 biological parents. Scoped to the acting clan: edges are
            # owned per-clan (created_by_clan_id), and persons are shared M:N across
            # clans, so another clan's parent edges must neither count against this
            # clan's limit nor be disclosed via the resulting error.
            bio_count = await self._q.count_bio_parents(child_id, clan_id, exclude_link_id)
            if bio_count >= 2:
                raise ConflictError("relationship.too_many_biological_parents")
            # Rule: a biological parent must be at least ~12 years older than the child.
            # This is a BIOLOGICAL floor only — an adoptive/step/foster parent may be any
            # age (e.g. an older sibling adopting), so it must not gate those types.
            if age_gap is not None and age_gap < 12:
                if both_exact:
                    raise BusinessRuleViolation(
                        "relationship.parent_too_young",
                        detail={"min_age_gap": 12, "actual": round(age_gap, 1)},
                    )
                # non-exact: an estimate can't justify a hard block (ADR-011) — advise only
                warning = (
                    f"Parent only {round(age_gap, 1)} years older than child (dates approximate)"
                )

        # Advisory (any relationship type): flag an unusually large age gap.
        if age_gap is not None and age_gap > 80:
            warning = f"Unusual age gap: {round(age_gap, 1)} years"

        # Rule: cycle detection. Skipped on update — parent_id/child_id are immutable
        # once created, so a type-only change cannot introduce a new cycle. Must run
        # regardless of the age-warning path above (previously the >80 branch
        # returned early and skipped this check entirely — fixed here).
        if check_cycle and await self._q.is_ancestor(parent_id, child_id, clan_id):
            raise BusinessRuleViolation("relationship.creates_cycle")

        return {"warning": warning} if warning else None

    async def check_duplicate_parent_child(
        self, parent_id: uuid.UUID, child_id: uuid.UUID, clan_id: uuid.UUID
    ) -> None:
        # Scoped to the acting clan: a duplicate is only a duplicate within the
        # clan that owns the edge. Cross-clan edges for a shared person are
        # legitimate and must not leak through this check (see validate_parent_child).
        if await self._q.has_parent_child_link(parent_id, child_id, clan_id):
            raise ConflictError("relationship.duplicate_parent_child")

    async def check_duplicate_marriage(
        self,
        person1_id: uuid.UUID,
        person2_id: uuid.UUID,
        clan_id: uuid.UUID,
        *,
        exclude_marriage_id: uuid.UUID | None = None,
    ) -> None:
        if await self._q.has_active_marriage(person1_id, person2_id, clan_id, exclude_marriage_id):
            raise ConflictError("relationship.duplicate_marriage")

    async def check_spouse_order(
        self,
        person_a: uuid.UUID,
        person_b: uuid.UUID,
        spouse_order: int | None,
        clan_id: uuid.UUID,
        *,
        exclude_marriage_id: uuid.UUID | None = None,
    ) -> None:
        """Active marriages of EITHER spouse must have distinct spouse_order
        (vợ cả/hai/ba). Two-sided: (person1_id, person2_id) is an unordered
        pair — either spouse may land in either column — so the conflict
        check must look at both endpoints, not just person1.

        "Active" = non-divorced (status <> 'divorced'): married, widowed, and
        separated marriages all participate in the uniqueness check; only
        divorced marriages are exempt, matching ``has_active_marriage``'s
        definition of active.
        """
        if spouse_order is None:
            return
        if await self._q.has_spouse_order_conflict(
            person_a, person_b, spouse_order, clan_id, exclude_marriage_id
        ):
            raise ConflictError("relationship.duplicate_spouse_order")
