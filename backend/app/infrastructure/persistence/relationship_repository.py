"""SQLAlchemy implementation of Relationship repositories + query port."""

from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.relationship.entities import Marriage as MarriageEntity
from app.domain.relationship.entities import ParentChild as ParentChildEntity
from app.domain.relationship.validator import BirthDate
from app.domain.shared.exceptions import ConflictError
from app.infrastructure.persistence.person_query_port import _no_deleted_endpoint
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.models.clan_membership import ClanMembership
from app.models.marriage import Marriage as MarriageModel
from app.models.parent_child import ParentChild as ParentChildModel
from app.models.person import Person as PersonModel

# ── Mappers (inline, these models are simpler) ──────────────────


def _marriage_to_domain(m: MarriageModel) -> MarriageEntity:
    return MarriageEntity(
        id=m.id,
        person1_id=m.person1_id,
        person2_id=m.person2_id,
        created_by_clan_id=m.created_by_clan_id,
        marriage_date=m.marriage_date,
        marriage_date_precision=m.marriage_date_precision,
        marriage_date_display=m.marriage_date_display,
        divorce_date=m.divorce_date,
        divorce_date_precision=m.divorce_date_precision,
        divorce_date_display=m.divorce_date_display,
        marriage_place=m.marriage_place,
        status=m.status,
        spouse_order=m.spouse_order,
        notes=m.notes,
        created_by=m.created_by,
        updated_by=m.updated_by,
        is_deleted=m.is_deleted,
        deleted_at=m.deleted_at,
        deleted_by=m.deleted_by,
        created_at=m.created_at,
        updated_at=m.updated_at,
        version=m.version,
    )


def _marriage_to_orm(e: MarriageEntity) -> MarriageModel:
    return MarriageModel(
        id=e.id,
        person1_id=e.person1_id,
        person2_id=e.person2_id,
        created_by_clan_id=e.created_by_clan_id,
        marriage_date=e.marriage_date,
        marriage_date_precision=e.marriage_date_precision,
        marriage_date_display=e.marriage_date_display,
        divorce_date=e.divorce_date,
        divorce_date_precision=e.divorce_date_precision,
        divorce_date_display=e.divorce_date_display,
        marriage_place=e.marriage_place,
        status=e.status,
        spouse_order=e.spouse_order,
        notes=e.notes,
        created_by=e.created_by,
        updated_by=e.updated_by,
        is_deleted=e.is_deleted,
        deleted_at=e.deleted_at,
        deleted_by=e.deleted_by,
        version=e.version,
    )


_MARRIAGE_UPDATABLE = (
    "marriage_date",
    "marriage_date_precision",
    "marriage_date_display",
    "divorce_date",
    "divorce_date_precision",
    "divorce_date_display",
    "marriage_place",
    "status",
    "spouse_order",
    "notes",
    "updated_by",
    "is_deleted",
    "deleted_at",
    "deleted_by",
)


def _pc_to_domain(m: ParentChildModel) -> ParentChildEntity:
    return ParentChildEntity(
        id=m.id,
        parent_id=m.parent_id,
        child_id=m.child_id,
        created_by_clan_id=m.created_by_clan_id,
        relationship_type=m.relationship_type,
        birth_order=m.birth_order,
        notes=m.notes,
        created_by=m.created_by,
        updated_by=m.updated_by,
        is_deleted=m.is_deleted,
        deleted_at=m.deleted_at,
        deleted_by=m.deleted_by,
        created_at=m.created_at,
        updated_at=m.updated_at,
        version=m.version,
    )


def _pc_to_orm(e: ParentChildEntity) -> ParentChildModel:
    return ParentChildModel(
        id=e.id,
        parent_id=e.parent_id,
        child_id=e.child_id,
        created_by_clan_id=e.created_by_clan_id,
        relationship_type=e.relationship_type,
        birth_order=e.birth_order,
        notes=e.notes,
        created_by=e.created_by,
        updated_by=e.updated_by,
        is_deleted=e.is_deleted,
        deleted_at=e.deleted_at,
        deleted_by=e.deleted_by,
        version=e.version,
    )


_PC_UPDATABLE = (
    "relationship_type",
    "birth_order",
    "notes",
    "updated_by",
    "is_deleted",
    "deleted_at",
    "deleted_by",
)


# ── Repositories ─────────────────────────────────────────────────


class SqlAlchemyMarriageRepository:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow
        self._session = uow.session

    async def get_by_id(self, marriage_id: uuid.UUID, clan_id: uuid.UUID) -> MarriageEntity | None:
        result = await self._session.execute(
            select(MarriageModel).where(
                MarriageModel.id == marriage_id,
                MarriageModel.created_by_clan_id == clan_id,
                MarriageModel.is_deleted.is_(False),
            )
        )
        model = result.scalar_one_or_none()
        return _marriage_to_domain(model) if model else None

    async def save(self, marriage: MarriageEntity, *, expected_version: int | None = None) -> None:
        self._uow.track(marriage)
        existing = await self._session.get(MarriageModel, marriage.id)
        if existing is None:
            self._session.add(_marriage_to_orm(marriage))
            return
        values = {f: getattr(marriage, f) for f in _MARRIAGE_UPDATABLE}
        stmt = (
            sql_update(MarriageModel)
            .where(MarriageModel.id == marriage.id)
            .values(**values, version=MarriageModel.version + 1)
        )
        if expected_version is not None:
            stmt = stmt.where(MarriageModel.version == expected_version)
        result = await self._session.execute(stmt)
        if result.rowcount == 0:
            current = await self._session.scalar(
                select(MarriageModel.version).where(MarriageModel.id == marriage.id)
            )
            raise ConflictError("stale_write", detail={"current_version": current})
        await self._session.refresh(existing)
        marriage.version = existing.version


class SqlAlchemyParentChildRepository:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow
        self._session = uow.session

    async def get_by_id(self, link_id: uuid.UUID, clan_id: uuid.UUID) -> ParentChildEntity | None:
        result = await self._session.execute(
            select(ParentChildModel).where(
                ParentChildModel.id == link_id,
                ParentChildModel.created_by_clan_id == clan_id,
                ParentChildModel.is_deleted.is_(False),
            )
        )
        model = result.scalar_one_or_none()
        return _pc_to_domain(model) if model else None

    async def save(self, link: ParentChildEntity, *, expected_version: int | None = None) -> None:
        self._uow.track(link)
        existing = await self._session.get(ParentChildModel, link.id)
        if existing is None:
            self._session.add(_pc_to_orm(link))
            return
        values = {f: getattr(link, f) for f in _PC_UPDATABLE}
        stmt = (
            sql_update(ParentChildModel)
            .where(ParentChildModel.id == link.id)
            .values(**values, version=ParentChildModel.version + 1)
        )
        if expected_version is not None:
            stmt = stmt.where(ParentChildModel.version == expected_version)
        result = await self._session.execute(stmt)
        if result.rowcount == 0:
            current = await self._session.scalar(
                select(ParentChildModel.version).where(ParentChildModel.id == link.id)
            )
            raise ConflictError("stale_write", detail={"current_version": current})
        await self._session.refresh(existing)
        link.version = existing.version


# ── Read ports (the by-id GETs) ──────────────────────────────────
#
# Deliberately not methods on the repositories above. Those load an edge for a
# write, and update and delete must keep reaching an edge whose endpoint person
# is soft-deleted — hiding the row there would leave it unreachable through the
# API entirely (ADR-051 § 8). These answer the read question instead.
#
# ``_no_deleted_endpoint`` is imported from ``person_query_port`` rather than
# copied. It stays private there because nothing outside
# ``app.infrastructure.persistence`` may use it, and it stays one definition
# because two copies of a visibility rule drift.


class SqlAlchemyMarriageReadPort:
    """Implements ``MarriageReadPort`` for ``GET /relationships/marriages/{id}``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_visible_by_id(
        self, marriage_id: uuid.UUID, clan_id: uuid.UUID
    ) -> MarriageEntity | None:
        result = await self._session.execute(
            select(MarriageModel).where(
                MarriageModel.id == marriage_id,
                MarriageModel.created_by_clan_id == clan_id,
                MarriageModel.is_deleted.is_(False),
                _no_deleted_endpoint(MarriageModel.person1_id, MarriageModel.person2_id),
            )
        )
        model = result.scalar_one_or_none()
        return _marriage_to_domain(model) if model else None


class SqlAlchemyParentChildReadPort:
    """Implements ``ParentChildReadPort`` for ``GET /relationships/parent-child/{id}``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_visible_by_id(
        self, link_id: uuid.UUID, clan_id: uuid.UUID
    ) -> ParentChildEntity | None:
        result = await self._session.execute(
            select(ParentChildModel).where(
                ParentChildModel.id == link_id,
                ParentChildModel.created_by_clan_id == clan_id,
                ParentChildModel.is_deleted.is_(False),
                _no_deleted_endpoint(ParentChildModel.parent_id, ParentChildModel.child_id),
            )
        )
        model = result.scalar_one_or_none()
        return _pc_to_domain(model) if model else None


# ── Query Port (for validator) ───────────────────────────────────


class SqlAlchemyRelationshipQueryPort:
    """Implements the RelationshipQueryPort protocol for domain validation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count_bio_parents(
        self,
        child_id: uuid.UUID,
        clan_id: uuid.UUID,
        exclude_link_id: uuid.UUID | None = None,
    ) -> int:
        result = await self._session.execute(
            text("""
                SELECT COUNT(*) FROM public.parent_child
                WHERE child_id = :child_id
                  AND created_by_clan_id = :clan_id
                  AND relationship_type = 'biological'
                  AND is_deleted = false
                  AND (CAST(:exclude_id AS uuid) IS NULL OR id != :exclude_id)
            """),
            {"child_id": child_id, "clan_id": clan_id, "exclude_id": exclude_link_id},
        )
        return int(result.scalar() or 0)

    async def has_active_marriage(
        self,
        person1_id: uuid.UUID,
        person2_id: uuid.UUID,
        clan_id: uuid.UUID,
        exclude_marriage_id: uuid.UUID | None = None,
    ) -> bool:
        result = await self._session.execute(
            text("""
                SELECT 1 FROM public.marriages
                WHERE (
                    (person1_id = :p1 AND person2_id = :p2)
                    OR (person1_id = :p2 AND person2_id = :p1)
                )
                AND created_by_clan_id = :clan_id
                AND status NOT IN ('divorced')
                AND is_deleted = false
                AND (CAST(:exclude_id AS uuid) IS NULL OR id != :exclude_id)
                LIMIT 1
            """),
            {
                "p1": person1_id,
                "p2": person2_id,
                "clan_id": clan_id,
                "exclude_id": exclude_marriage_id,
            },
        )
        return result.first() is not None

    async def has_spouse_order_conflict(
        self,
        person_a: uuid.UUID,
        person_b: uuid.UUID,
        spouse_order: int,
        clan_id: uuid.UUID,
        exclude_marriage_id: uuid.UUID | None = None,
    ) -> bool:
        result = await self._session.execute(
            text("""
                SELECT 1 FROM public.marriages
                WHERE spouse_order = :so
                  AND created_by_clan_id = :clan_id
                  AND status <> 'divorced' AND is_deleted = false
                  AND (person1_id IN (:a, :b) OR person2_id IN (:a, :b))
                  AND (CAST(:exclude_id AS uuid) IS NULL OR id != :exclude_id)
                LIMIT 1
            """),
            {
                "a": person_a,
                "b": person_b,
                "so": spouse_order,
                "clan_id": clan_id,
                "exclude_id": exclude_marriage_id,
            },
        )
        return result.first() is not None

    async def has_parent_child_link(
        self, parent_id: uuid.UUID, child_id: uuid.UUID, clan_id: uuid.UUID
    ) -> bool:
        result = await self._session.execute(
            text("""
                SELECT 1 FROM public.parent_child
                WHERE parent_id = :parent_id
                  AND child_id = :child_id
                  AND created_by_clan_id = :clan_id
                  AND is_deleted = false
                LIMIT 1
            """),
            {"parent_id": parent_id, "child_id": child_id, "clan_id": clan_id},
        )
        return result.first() is not None

    async def is_ancestor(
        self, descendant_id: uuid.UUID, ancestor_id: uuid.UUID, clan_id: uuid.UUID
    ) -> bool:
        """Unbounded ancestor walk for cycle detection (M1).

        Deliberately NOT get_ancestors_flat: that is a display function with a
        depth cap. Cycle detection must see the whole chain — deep gia phả
        (>20 đời) previously slipped through. The path-array guard terminates
        traversal even on already-corrupt (cyclic) data.
        """
        result = await self._session.execute(
            text("""
                WITH RECURSIVE ancestors AS (
                    SELECT pc.parent_id AS person_id,
                           ARRAY[pc.child_id, pc.parent_id] AS path
                    FROM public.parent_child pc
                    WHERE pc.child_id = :descendant_id
                      AND pc.created_by_clan_id = :clan_id
                      AND pc.is_deleted = false
                    UNION ALL
                    SELECT pc.parent_id, a.path || pc.parent_id
                    FROM public.parent_child pc
                    JOIN ancestors a ON pc.child_id = a.person_id
                    WHERE pc.created_by_clan_id = :clan_id
                      AND pc.is_deleted = false
                      AND NOT pc.parent_id = ANY(a.path)
                )
                SELECT 1 FROM ancestors WHERE person_id = :ancestor_id LIMIT 1
            """),
            {"descendant_id": descendant_id, "ancestor_id": ancestor_id, "clan_id": clan_id},
        )
        return result.first() is not None

    async def get_birth_dates(self, person_ids: list[uuid.UUID]) -> dict[uuid.UUID, BirthDate]:
        """A soft-deleted person is invisible here, matching the read paths
        (M3, review 2026-07-18).

        Carries ``birth_date_precision`` alongside the value (M5) so the domain
        validator can tell an 'exact' date from a 'circa'/'year'/'month'/'unknown'
        estimate before hard-blocking on it."""
        if not person_ids:
            return {}
        stmt = select(
            PersonModel.id, PersonModel.birth_date, PersonModel.birth_date_precision
        ).where(
            PersonModel.id.in_(person_ids),
            PersonModel.is_deleted.is_(False),
        )
        result = await self._session.execute(stmt)
        return {
            row.id: BirthDate(value=row.birth_date, precision=row.birth_date_precision)
            for row in result
        }

    async def persons_in_clan(
        self, person_ids: list[uuid.UUID], clan_id: uuid.UUID
    ) -> set[uuid.UUID]:
        """Subset of person_ids that are members of clan_id (clan_memberships).

        Mirrors the read-path definition of "person in clan" used by
        PersonRepository.get_in_clan. A soft-deleted person is invisible here,
        matching the read paths (M3, review 2026-07-18).
        """
        if not person_ids:
            return set()
        stmt = (
            select(ClanMembership.person_id)
            .join(PersonModel, PersonModel.id == ClanMembership.person_id)
            .where(
                ClanMembership.person_id.in_(person_ids),
                ClanMembership.clan_id == clan_id,
                PersonModel.is_deleted.is_(False),
            )
        )
        result = await self._session.execute(stmt)
        return set(result.scalars().all())
