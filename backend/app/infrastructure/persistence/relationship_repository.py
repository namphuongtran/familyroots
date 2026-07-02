"""SQLAlchemy implementation of Relationship repositories + query port."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.relationship.entities import Marriage as MarriageEntity
from app.domain.relationship.entities import ParentChild as ParentChildEntity
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
        divorce_date=m.divorce_date,
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
    )


def _marriage_to_orm(e: MarriageEntity) -> MarriageModel:
    return MarriageModel(
        id=e.id,
        person1_id=e.person1_id,
        person2_id=e.person2_id,
        created_by_clan_id=e.created_by_clan_id,
        marriage_date=e.marriage_date,
        divorce_date=e.divorce_date,
        marriage_place=e.marriage_place,
        status=e.status,
        spouse_order=e.spouse_order,
        notes=e.notes,
        created_by=e.created_by,
        updated_by=e.updated_by,
        is_deleted=e.is_deleted,
        deleted_at=e.deleted_at,
        deleted_by=e.deleted_by,
    )


_MARRIAGE_UPDATABLE = (
    "marriage_date",
    "divorce_date",
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

    async def save(self, marriage: MarriageEntity) -> None:
        self._uow.track(marriage)
        existing = await self._session.get(MarriageModel, marriage.id)
        if existing:
            for f in _MARRIAGE_UPDATABLE:
                setattr(existing, f, getattr(marriage, f))
        else:
            self._session.add(_marriage_to_orm(marriage))


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

    async def save(self, link: ParentChildEntity) -> None:
        self._uow.track(link)
        existing = await self._session.get(ParentChildModel, link.id)
        if existing:
            for f in _PC_UPDATABLE:
                setattr(existing, f, getattr(link, f))
        else:
            self._session.add(_pc_to_orm(link))


# ── Query Port (for validator) ───────────────────────────────────


class SqlAlchemyRelationshipQueryPort:
    """Implements the RelationshipQueryPort protocol for domain validation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count_bio_parents(self, child_id: uuid.UUID) -> int:
        result = await self._session.execute(
            text("""
                SELECT COUNT(*) FROM public.parent_child
                WHERE child_id = :child_id
                  AND relationship_type = 'biological'
                  AND is_deleted = false
            """),
            {"child_id": child_id},
        )
        return int(result.scalar() or 0)

    async def has_active_marriage(self, person1_id: uuid.UUID, person2_id: uuid.UUID) -> bool:
        result = await self._session.execute(
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
        return result.first() is not None

    async def has_parent_child_link(self, parent_id: uuid.UUID, child_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            text("""
                SELECT 1 FROM public.parent_child
                WHERE parent_id = :parent_id
                  AND child_id = :child_id
                  AND is_deleted = false
                LIMIT 1
            """),
            {"parent_id": parent_id, "child_id": child_id},
        )
        return result.first() is not None

    async def is_ancestor(
        self, descendant_id: uuid.UUID, ancestor_id: uuid.UUID, clan_id: uuid.UUID
    ) -> bool:
        ancestors = await self._session.execute(
            text("SELECT person_id FROM public.get_ancestors_flat(:id, :clan_id, 20)"),
            {"id": descendant_id, "clan_id": clan_id},
        )
        ancestor_ids = {row[0] for row in ancestors}
        return ancestor_id in ancestor_ids

    async def get_birth_dates(self, person_ids: list[uuid.UUID]) -> dict[uuid.UUID, date | None]:
        if not person_ids:
            return {}
        stmt = select(PersonModel.id, PersonModel.birth_date).where(PersonModel.id.in_(person_ids))
        result = await self._session.execute(stmt)
        return {row.id: row.birth_date for row in result}

    async def persons_in_clan(
        self, person_ids: list[uuid.UUID], clan_id: uuid.UUID
    ) -> set[uuid.UUID]:
        """Subset of person_ids that are members of clan_id (clan_memberships).

        Mirrors the read-path definition of "person in clan" used by
        PersonRepository.get_in_clan.
        """
        if not person_ids:
            return set()
        stmt = select(ClanMembership.person_id).where(
            ClanMembership.person_id.in_(person_ids),
            ClanMembership.clan_id == clan_id,
        )
        result = await self._session.execute(stmt)
        return set(result.scalars().all())
