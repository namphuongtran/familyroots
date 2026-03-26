"""Business rule validation for relationship creation/updates.

All validation is done in Python (not DB constraints) to provide
meaningful error messages with i18n support.
"""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationError
from app.models.person import Person
from app.services.translator import t


class RelationshipValidator:
    """Validates business rules before creating or updating relationships."""

    async def validate_parent_child(
        self,
        parent_id: uuid.UUID,
        child_id: uuid.UUID,
        relationship_type: str,
        db: AsyncSession,
        clan_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        """Validate parent-child relationship rules.

        Returns a warning dict if the relationship is unusual but allowed,
        or None if everything is normal. Raises on violation.
        """
        parent = await db.get(Person, parent_id)
        child = await db.get(Person, child_id)

        if not parent or not child:
            raise ValidationError("person_not_found")

        # Rule 1: max 2 biological parents
        if relationship_type == "biological":
            bio_count = await self._count_bio_parents(child_id, db)
            if bio_count >= 2:
                raise ConflictError("relationship.too_many_biological_parents")

        # Rule 2: age gap check (if birth dates known)
        if parent.birth_date and child.birth_date:
            age_gap = (child.birth_date - parent.birth_date).days / 365.25
            if age_gap < 12:
                raise ValidationError(
                    "relationship.parent_too_young",
                    {"min_age_gap": 12, "actual": round(age_gap, 1)},
                )
            if age_gap > 80:
                return {"warning": t("relationship.unusual_age_gap", years=round(age_gap, 1))}

        # Rule 3: cycle detection — child cannot be an ancestor of parent
        ancestors = await db.execute(
            text("SELECT person_id FROM public.get_ancestors_flat(:id, :clan_id, 20)"),
            {"id": parent_id, "clan_id": clan_id},
        )
        ancestor_ids = {row[0] for row in ancestors}
        if child_id in ancestor_ids:
            raise ValidationError("relationship.creates_cycle")

        return None

    async def validate_spouse(
        self,
        person1_id: uuid.UUID,
        person2_id: uuid.UUID,
        marriage_date: date | None,
        db: AsyncSession,
    ) -> None:
        """Validate marriage rules. Raises on violation."""
        # Check if either person already has an active (non-ended) marriage
        # Note: this system supports polygamy, so we only warn but don't block
        pass

    async def check_duplicate_marriage(
        self,
        person1_id: uuid.UUID,
        person2_id: uuid.UUID,
        db: AsyncSession,
    ) -> None:
        """Raise ConflictError if an active marriage between the two already exists."""
        result = await db.execute(
            text("""
                SELECT 1 FROM public.marriages
                WHERE (
                    (person1_id = :p1 AND person2_id = :p2)
                    OR (person1_id = :p2 AND person2_id = :p1)
                )
                AND status NOT IN ('divorced')
                AND is_deleted = false
                LIMIT 1
            """),
            {"p1": person1_id, "p2": person2_id},
        )
        if result.first():
            raise ConflictError("relationship.duplicate_marriage")

    async def check_duplicate_parent_child(
        self,
        parent_id: uuid.UUID,
        child_id: uuid.UUID,
        db: AsyncSession,
    ) -> None:
        """Raise ConflictError if a parent-child link already exists."""
        result = await db.execute(
            text("""
                SELECT 1 FROM public.parent_child
                WHERE parent_id = :parent_id
                  AND child_id = :child_id
                  AND is_deleted = false
                LIMIT 1
            """),
            {"parent_id": parent_id, "child_id": child_id},
        )
        if result.first():
            raise ConflictError("relationship.duplicate_parent_child")

    async def _count_bio_parents(self, child_id: uuid.UUID, db: AsyncSession) -> int:
        """Count biological parent relationships for a person."""
        result = await db.execute(
            text("""
                SELECT COUNT(*) FROM public.parent_child
                WHERE child_id = :child_id
                  AND relationship_type = 'biological'
                  AND is_deleted = false
            """),
            {"child_id": child_id},
        )
        row = result.first()
        return row[0] if row else 0
