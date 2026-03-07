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
from app.models.member import Member
from app.services.translator import t


class RelationshipValidator:
    """Validates business rules before creating or updating relationships."""

    async def validate_parent_child(
        self,
        parent_id: uuid.UUID,
        child_id: uuid.UUID,
        subtype: str,
        db: AsyncSession,
        clan_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        """Validate parent-child relationship rules.

        Returns a warning dict if the relationship is unusual but allowed,
        or None if everything is normal. Raises on violation.
        """
        parent = await db.get(Member, parent_id)
        child = await db.get(Member, child_id)

        if not parent or not child:
            raise ValidationError("member_not_found")

        # Rule 1: max 2 biological parents
        if subtype == "biological":
            bio_count = await self._count_bio_parents(child_id, clan_id, db)
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
                return {
                    "warning": t(
                        "relationship.unusual_age_gap", years=round(age_gap, 1)
                    )
                }

        # Rule 3: cycle detection — child cannot be an ancestor of parent
        ancestors = await db.execute(
            text(
                "SELECT member_id FROM public.get_ancestors_flat(:id, :clan_id, 20)"
            ),
            {"id": parent_id, "clan_id": clan_id},
        )
        ancestor_ids = {row[0] for row in ancestors}
        if child_id in ancestor_ids:
            raise ValidationError("relationship.creates_cycle")

        return None

    async def validate_spouse(
        self,
        member_id: uuid.UUID,
        spouse_id: uuid.UUID,
        start_date: date | None,
        db: AsyncSession,
        clan_id: uuid.UUID,
    ) -> None:
        """Validate spouse relationship rules. Raises on violation."""
        for person_id in [member_id, spouse_id]:
            existing = await db.execute(
                text("""
                    SELECT 1 FROM public.relationships
                    WHERE clan_id = :clan_id
                      AND relation_type = 'spouse'
                      AND end_date IS NULL
                      AND (member_id = :pid OR related_id = :pid)
                    LIMIT 1
                """),
                {"clan_id": clan_id, "pid": person_id},
            )
            if existing.first():
                raise ConflictError(
                    "relationship.already_married",
                    {"member_id": str(person_id)},
                )

    async def check_duplicate_edge(
        self,
        member_id: uuid.UUID,
        related_id: uuid.UUID,
        relation_type: str,
        clan_id: uuid.UUID,
        db: AsyncSession,
    ) -> None:
        """Raise ConflictError if an identical active relationship already exists."""
        result = await db.execute(
            text("""
                SELECT 1 FROM public.relationships
                WHERE clan_id = :clan_id
                  AND member_id = :member_id
                  AND related_id = :related_id
                  AND relation_type = :rtype
                  AND end_date IS NULL
                LIMIT 1
            """),
            {
                "clan_id": clan_id,
                "member_id": member_id,
                "related_id": related_id,
                "rtype": relation_type,
            },
        )
        if result.first():
            raise ConflictError("relationship.duplicate_edge")

    async def _count_bio_parents(
        self, child_id: uuid.UUID, clan_id: uuid.UUID, db: AsyncSession
    ) -> int:
        """Count biological parent relationships for a member."""
        result = await db.execute(
            text("""
                SELECT COUNT(*) FROM public.relationships
                WHERE clan_id = :clan_id
                  AND related_id = :child_id
                  AND relation_type = 'parent'
                  AND relation_subtype = 'biological'
            """),
            {"clan_id": clan_id, "child_id": child_id},
        )
        row = result.first()
        return row[0] if row else 0
