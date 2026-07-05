"""SQLAlchemy implementation of TreeRepository."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clan_membership import ClanMembership
from app.models.person import Person
from app.services.tree_builder import build_descendants_tree, find_clan_founder


class SqlAlchemyTreeRepository:
    """TreeRepository backed by SQLAlchemy + existing tree_builder service."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def person_in_clan(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(Person)
            .join(ClanMembership, ClanMembership.person_id == Person.id)
            .where(
                Person.id == person_id,
                ClanMembership.clan_id == clan_id,
                Person.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none() is not None

    async def find_clan_founder(self, clan_id: uuid.UUID) -> uuid.UUID | None:
        return await find_clan_founder(self._session, clan_id)

    async def build_descendants_tree(
        self,
        root_id: uuid.UUID,
        clan_id: uuid.UUID,
        max_generations: int,
    ) -> dict[str, Any] | None:
        return await build_descendants_tree(self._session, root_id, clan_id, max_generations)

    async def get_ancestors(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text(
                "WITH RECURSIVE ancestors AS ("
                "  SELECT p.id, p.full_name, p.gender, p.birth_date, p.death_date, "
                "         p.avatar_url, cm.generation, pc.parent_id, 0 AS depth "
                "  FROM public.persons p "
                "  LEFT JOIN public.clan_memberships cm "
                "    ON cm.person_id = p.id AND cm.clan_id = :clan_id "
                "  LEFT JOIN public.parent_child pc "
                "    ON pc.child_id = p.id AND pc.is_deleted = false "
                "       AND pc.created_by_clan_id = :clan_id "
                "  WHERE p.id = :person_id AND p.is_deleted = false "
                "  UNION ALL "
                "  SELECT p.id, p.full_name, p.gender, p.birth_date, p.death_date, "
                "         p.avatar_url, cm.generation, pc.parent_id, a.depth + 1 "
                "  FROM ancestors a "
                "  JOIN public.persons p ON p.id = a.parent_id "
                "  LEFT JOIN public.clan_memberships cm "
                "    ON cm.person_id = p.id AND cm.clan_id = :clan_id "
                "  LEFT JOIN public.parent_child pc "
                "    ON pc.child_id = p.id AND pc.is_deleted = false "
                "       AND pc.created_by_clan_id = :clan_id "
                "  WHERE p.is_deleted = false "
                "    AND a.depth < 50 "
                ") "
                "SELECT id, full_name, gender, birth_date, death_date, "
                "       avatar_url, generation, parent_id, depth "
                "FROM ancestors ORDER BY depth ASC"
            ),
            {"person_id": person_id, "clan_id": clan_id},
        )
        rows = result.mappings().all()
        return [
            {
                "id": str(row["id"]),
                "full_name": row["full_name"],
                "gender": row["gender"],
                "birth_date": row["birth_date"].isoformat() if row["birth_date"] else None,
                "death_date": row["death_date"].isoformat() if row["death_date"] else None,
                "avatar_url": row["avatar_url"],
                "generation": row["generation"],
                "depth": row["depth"],
            }
            for row in rows
        ]

    async def find_path(
        self, from_id: uuid.UUID, to_id: uuid.UUID, clan_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text("""
                SELECT p.person_id, p.full_name, p.gender, p.edge_type,
                       per.avatar_url, per.birth_date, per.birth_date_approx
                FROM public.find_relationship_path(:from_id, :to_id, :clan_id) p
                LEFT JOIN public.persons per ON p.person_id = per.id
                ORDER BY p.step
            """),
            {"from_id": from_id, "to_id": to_id, "clan_id": clan_id},
        )
        rows = result.mappings().all()
        return [
            {
                "person_id": str(row["person_id"]),
                "full_name": row["full_name"],
                "gender": row.get("gender", "unknown"),
                "edge_type": row.get("edge_type"),
                "avatar_url": row.get("avatar_url"),
                # birth_date (+ _approx) thread through so the kinship descriptor can pick
                # age-specific terms (bác vs chú, anh/chị vs em). An APPROXIMATE date must
                # not yield a hard older/younger claim, so the flag travels with it.
                "birth_date": row.get("birth_date"),
                "birth_date_approx": row.get("birth_date_approx", False),
            }
            for row in rows
        ]
