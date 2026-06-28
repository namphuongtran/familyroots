"""SQLAlchemy implementation of PersonRepository.

Encapsulates all Person persistence logic including the trigram/unaccent
full-text search that was previously inline in the route handler.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.person.entity import Person as PersonEntity
from app.domain.person.repository import PersonFilters, PersonSearchResult
from app.infrastructure.persistence.person_mapper import apply_to_orm, to_domain, to_orm
from app.models.clan_membership import ClanMembership
from app.models.person import Person as PersonModel
from app.models.user_profile import UserProfile


class SqlAlchemyPersonRepository:
    """Concrete Person repository backed by SQLAlchemy + PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, person_id: uuid.UUID) -> PersonEntity | None:
        result = await self._session.get(PersonModel, person_id)
        return to_domain(result) if result else None

    async def get_in_clan(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> PersonEntity | None:
        """Fetch person only if they have a membership in the given clan."""
        stmt = (
            select(PersonModel)
            .join(
                ClanMembership,
                ClanMembership.person_id == PersonModel.id,
            )
            .where(
                PersonModel.id == person_id,
                ClanMembership.clan_id == clan_id,
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return to_domain(model) if model else None

    async def get_linked_person_id(self, user_id: uuid.UUID) -> uuid.UUID | None:
        result = await self._session.execute(
            select(UserProfile.person_id).where(UserProfile.id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_in_clan(
        self,
        clan_id: uuid.UUID,
        filters: PersonFilters,
        cursor: str | None = None,
        limit: int = 50,
    ) -> list[PersonEntity]:
        stmt = (
            select(PersonModel)
            .join(
                ClanMembership,
                ClanMembership.person_id == PersonModel.id,
            )
            .where(ClanMembership.clan_id == clan_id)
            .where(PersonModel.is_deleted == filters.is_deleted)
        )

        if filters.gender:
            stmt = stmt.where(PersonModel.gender == filters.gender)
        if filters.generation is not None:
            stmt = stmt.where(ClanMembership.generation == filters.generation)
        if filters.branch_id is not None:
            stmt = stmt.where(ClanMembership.branch_id == filters.branch_id)

        # Cursor-based pagination (by created_at or ID)
        if cursor:
            stmt = stmt.where(PersonModel.id > uuid.UUID(cursor))

        stmt = stmt.order_by(PersonModel.full_name).limit(limit)

        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [to_domain(m) for m in models]

    async def search(
        self,
        clan_id: uuid.UUID,
        query: str,
        limit: int = 10,
    ) -> list[PersonSearchResult]:
        """Trigram/unaccent search — encapsulates the raw SQL that was
        previously inline in the persons route handler."""
        stmt = text("""
            SELECT p.id, p.full_name, p.birth_name, p.birth_date,
                 p.gender, p.avatar_url, cm.generation, cm.role AS membership_role,
                 cm.is_founder
            FROM persons p
            JOIN clan_memberships cm ON cm.person_id = p.id
            WHERE cm.clan_id = :clan_id
              AND p.is_deleted = false
              AND (
                  unaccent(lower(p.full_name)) ILIKE '%' || unaccent(lower(:q)) || '%'
                  OR unaccent(lower(COALESCE(p.birth_name, '')))
                     ILIKE '%' || unaccent(lower(:q)) || '%'
              )
            ORDER BY similarity(unaccent(lower(p.full_name)), unaccent(lower(:q))) DESC
            LIMIT :lim
        """)
        result = await self._session.execute(stmt, {"clan_id": clan_id, "q": query, "lim": limit})
        rows = result.mappings().all()
        return [
            PersonSearchResult(
                id=row["id"],
                full_name=row["full_name"],
                birth_name=row["birth_name"],
                birth_date=row["birth_date"],
                gender=row["gender"],
                avatar_url=row["avatar_url"],
                generation=row["generation"],
                membership_role=row["membership_role"],
                is_founder=row["is_founder"],
            )
            for row in rows
        ]

    async def save(self, person: PersonEntity) -> None:
        """Insert or update a Person."""
        existing = await self._session.get(PersonModel, person.id)
        if existing:
            apply_to_orm(person, existing)
        else:
            model = to_orm(person)
            self._session.add(model)

    async def save_with_membership(
        self,
        person: PersonEntity,
        clan_id: uuid.UUID,
        role: str = "blood",
        generation: int | None = None,
        is_founder: bool = False,
        branch_id: uuid.UUID | None = None,
    ) -> None:
        """Save a Person and its ClanMembership atomically."""
        model = to_orm(person)
        self._session.add(model)

        membership = ClanMembership(
            person_id=person.id,
            clan_id=clan_id,
            role=role,
            generation=generation,
            is_founder=is_founder,
            branch_id=branch_id,
        )
        self._session.add(membership)

    async def count_in_clan(self, clan_id: uuid.UUID, is_deleted: bool = False) -> int:
        stmt = (
            select(func.count())
            .select_from(PersonModel)
            .join(ClanMembership, ClanMembership.person_id == PersonModel.id)
            .where(
                ClanMembership.clan_id == clan_id,
                PersonModel.is_deleted == is_deleted,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def get_stats_for_persons(
        self, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, int]]:
        if not person_ids:
            return {}
        stmt = text("""
            SELECT p.id,
                (SELECT COUNT(*) FROM public.marriages m
                 WHERE (m.person1_id=p.id OR m.person2_id=p.id)
                 AND m.is_deleted=false) as spouse_count,
                (SELECT COUNT(*) FROM public.parent_child pc
                 WHERE pc.parent_id=p.id
                 AND pc.is_deleted=false) as child_count
            FROM public.persons p
            WHERE p.id = ANY(:pids)
        """).bindparams(pids=[str(pid) for pid in person_ids])
        result = await self._session.execute(stmt)
        return {
            uuid.UUID(str(row["id"])): {
                "spouse_count": row["spouse_count"],
                "child_count": row["child_count"],
            }
            for row in result.mappings().all()
        }
