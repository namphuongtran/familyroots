"""SQLAlchemy implementation of TreeRepository."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clan_membership import ClanMembership
from app.models.person import Person
from app.schemas.historical_date import to_historical_date
from app.services.tree_builder import build_descendants_tree, build_focus_view, find_clan_founder


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
        base_generation: int | None = None,
    ) -> dict[str, Any] | None:
        return await build_descendants_tree(
            self._session, root_id, clan_id, max_generations, base_generation
        )

    async def get_ancestors_flat(
        self, person_id: uuid.UUID, clan_id: uuid.UUID, max_generations: int = 50
    ) -> list[dict[str, Any]]:
        """Ancestor chain via the cycle-guarded, clan-scoped SQL function (no fan-out dup).

        Rows are ordered by depth ASC (the person itself is depth 0). Includes ``child_id``
        and raw ``generation`` for callers that need them (the focus handler)."""
        result = await self._session.execute(
            text(
                "SELECT person_id, full_name, gender, birth_date, "
                "       birth_date_precision, birth_date_display, "
                "       death_date, death_date_precision, death_date_display, "
                "       generation, avatar_url, child_id, depth "
                "FROM public.get_ancestors_flat(:person_id, :clan_id, :max_generations) "
                "ORDER BY depth ASC"
            ),
            {"person_id": person_id, "clan_id": clan_id, "max_generations": max_generations},
        )
        return [
            {
                "id": str(row["person_id"]),
                "full_name": row["full_name"],
                "gender": row["gender"],
                "birth_date": to_historical_date(
                    row["birth_date"], row["birth_date_precision"], row["birth_date_display"], None
                ).model_dump(),
                "death_date": to_historical_date(
                    row["death_date"], row["death_date_precision"], row["death_date_display"], None
                ).model_dump(),
                "avatar_url": row["avatar_url"],
                "generation": row["generation"],
                "child_id": str(row["child_id"]) if row["child_id"] else None,
                "depth": row["depth"],
            }
            for row in result.mappings().all()
        ]

    async def get_ancestors(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        """Public ancestor list for /tree/ancestors. Delegates to the flat walk and drops
        the internal ``child_id`` so the endpoint contract is unchanged.

        ``get_ancestors_flat`` returns one row per *lineage edge*: a shared ancestor
        reached through two different children (pedigree collapse, e.g. two parents
        with a common parent) legitimately appears once per lineage there, since each
        row also carries the ``child_id`` needed to draw that edge. This public list
        has no per-edge concept, so it dedupes by person id, keeping the first
        occurrence — rows are already ``depth ASC`` so that is the shallowest depth."""
        rows = await self.get_ancestors_flat(person_id, clan_id)
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for row in rows:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            deduped.append({k: v for k, v in row.items() if k != "child_id"})
        return deduped

    async def build_focus_view(
        self,
        focus_id: uuid.UUID,
        clan_id: uuid.UUID,
        descendant_depth: int,
        base_generation: int | None,
    ) -> dict[str, Any]:
        return await build_focus_view(
            self._session, focus_id, clan_id, descendant_depth, base_generation
        )

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
