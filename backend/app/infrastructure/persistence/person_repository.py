"""SQLAlchemy implementation of PersonRepository.

Encapsulates all Person persistence logic including the trigram/unaccent
full-text search that was previously inline in the route handler.
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy import update as sql_update

from app.core.exceptions import AppError
from app.core.pagination import decode_fields_cursor
from app.domain.person.entity import Person as PersonEntity
from app.domain.person.repository import PersonFilters, PersonSearchResult
from app.domain.shared.exceptions import ConflictError
from app.infrastructure.persistence.person_mapper import UPDATABLE_FIELDS, to_domain, to_orm
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.models.clan_membership import ClanMembership
from app.models.person import Person as PersonModel
from app.models.user_profile import UserProfile

# Search SQL, module-level so it can be EXPLAIN-checked in tests. The filter and
# ORDER BY use `public.f_unaccent(<col>)` — the EXACT expression the GIN trigram
# indexes are built on (idx_persons_fullname_trgm / idx_persons_birthname_trgm,
# migration 009). Using `unaccent(lower(...))` instead (as before) makes the
# expression differ from the index and forces a full sequential scan.
_SEARCH_SQL = """
    SELECT p.id, p.full_name, p.birth_name, p.birth_date,
         p.birth_date_precision, p.birth_date_display, p.lunar_birth_date,
         p.gender, p.avatar_url, p.version, cm.generation, cm.role AS membership_role,
         cm.is_founder
    FROM persons p
    JOIN clan_memberships cm ON cm.person_id = p.id
    WHERE cm.clan_id = :clan_id
      AND p.is_deleted = false
      AND (
          public.f_unaccent(p.full_name) ILIKE '%' || public.f_unaccent(:q) || '%'
          OR public.f_unaccent(p.birth_name) ILIKE '%' || public.f_unaccent(:q) || '%'
      )
    ORDER BY similarity(public.f_unaccent(p.full_name), public.f_unaccent(:q)) DESC
    LIMIT :lim
"""


class SqlAlchemyPersonRepository:
    """Concrete Person repository backed by SQLAlchemy + PostgreSQL."""

    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        # Take the UoW (not a bare session) so save()/save_with_membership() can
        # auto-track the aggregate — tracking can't be forgotten at the seam.
        self._uow = uow
        self._session = uow.session

    async def get_in_clan(
        self, person_id: uuid.UUID, clan_id: uuid.UUID, include_deleted: bool = False
    ) -> PersonEntity | None:
        """Fetch person only if they have a membership in the given clan.

        Excludes soft-deleted persons unless ``include_deleted=True`` (the restore
        path needs to load an already-deleted person)."""
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
        if not include_deleted:
            stmt = stmt.where(PersonModel.is_deleted.is_(False))
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return to_domain(model) if model else None

    async def get_many_in_clan(
        self, person_ids: list[uuid.UUID], clan_id: uuid.UUID
    ) -> list[PersonEntity]:
        """Fetch every requested person that is a live member of the clan — one
        query, not one per id (the batch endpoint's person fan-out)."""
        if not person_ids:
            return []
        result = await self._session.execute(
            select(PersonModel)
            .join(ClanMembership, ClanMembership.person_id == PersonModel.id)
            .where(
                PersonModel.id.in_(person_ids),
                ClanMembership.clan_id == clan_id,
                PersonModel.is_deleted.is_(False),
            )
        )
        return [to_domain(m) for m in result.scalars().all()]

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

        # Cursor-based pagination: the list is ordered by (full_name, id), so the
        # cursor must carry both — an id-only cursor would skip/duplicate rows
        # whenever id-order and full_name-order disagree.
        if cursor:
            decoded = decode_fields_cursor(cursor)
            try:
                cursor_name = decoded["full_name"]
                cursor_id = uuid.UUID(decoded["id"])
            except (KeyError, ValueError, TypeError) as exc:
                raise AppError(400, "invalid_cursor") from exc
            stmt = stmt.where(
                or_(
                    PersonModel.full_name > cursor_name,
                    and_(
                        PersonModel.full_name == cursor_name,
                        PersonModel.id > cursor_id,
                    ),
                )
            )

        # Fetch one extra row so the caller can detect has_more without a COUNT query.
        stmt = stmt.order_by(PersonModel.full_name, PersonModel.id).limit(limit + 1)

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
        stmt = text(_SEARCH_SQL)
        result = await self._session.execute(stmt, {"clan_id": clan_id, "q": query, "lim": limit})
        rows = result.mappings().all()
        return [
            PersonSearchResult(
                id=row["id"],
                full_name=row["full_name"],
                birth_name=row["birth_name"],
                birth_date=row["birth_date"],
                birth_date_precision=row["birth_date_precision"],
                birth_date_display=row["birth_date_display"],
                lunar_birth_date=row["lunar_birth_date"],
                gender=row["gender"],
                avatar_url=row["avatar_url"],
                version=row["version"],
                generation=row["generation"],
                membership_role=row["membership_role"],
                is_founder=row["is_founder"],
            )
            for row in rows
        ]

    async def save(self, person: PersonEntity, *, expected_version: int | None = None) -> None:
        """Insert, or update with an optimistic-concurrency check (ADR-017).

        expected_version=None (delete/restore/claim paths) updates unconditionally
        but still bumps version so any concurrent PATCH sees a stale_write.
        """
        self._uow.track(person)
        existing = await self._session.get(PersonModel, person.id)
        if existing is None:
            self._session.add(to_orm(person))
            return

        values = {f: getattr(person, f) for f in UPDATABLE_FIELDS}
        stmt = (
            sql_update(PersonModel)
            .where(PersonModel.id == person.id)
            .values(**values, version=PersonModel.version + 1)
        )
        if expected_version is not None:
            stmt = stmt.where(PersonModel.version == expected_version)
        result = await self._session.execute(stmt)
        if result.rowcount == 0:
            current = await self._session.scalar(
                select(PersonModel.version).where(PersonModel.id == person.id)
            )
            raise ConflictError("stale_write", detail={"current_version": current})
        await self._session.refresh(existing)  # sync identity map with the core UPDATE
        person.version = existing.version

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
        self._uow.track(person)
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
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, int]]:
        if not person_ids:
            return {}
        # Counts are scoped to edges owned by the caller's clan (created_by_clan_id);
        # otherwise spouse/child counts would leak the existence of cross-clan edges.
        stmt = text("""
            SELECT p.id,
                (SELECT COUNT(*) FROM public.marriages m
                 WHERE (m.person1_id=p.id OR m.person2_id=p.id)
                 AND m.is_deleted=false
                 AND m.created_by_clan_id=:clan_id) as spouse_count,
                (SELECT COUNT(*) FROM public.parent_child pc
                 WHERE pc.parent_id=p.id
                 AND pc.is_deleted=false
                 AND pc.created_by_clan_id=:clan_id) as child_count
            FROM public.persons p
            WHERE p.id = ANY(:pids)
        """).bindparams(pids=person_ids, clan_id=clan_id)
        result = await self._session.execute(stmt)
        return {
            uuid.UUID(str(row["id"])): {
                "spouse_count": row["spouse_count"],
                "child_count": row["child_count"],
            }
            for row in result.mappings().all()
        }
