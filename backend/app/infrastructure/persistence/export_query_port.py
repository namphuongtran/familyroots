"""SQLAlchemy implementation of the clan export query port.

Archival dump: every query is a plain `SELECT *`-shaped `text()` statement
(acceptable here — this is a lossless clan export, not a normal CQRS read
model) rather than going through the ORM/schemas layer. Soft-deleted rows are
deliberately NOT filtered for persons/marriages/parent_child (the archive
keeps history, flagged); documents are live-only.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.export.ports import ExportQueryPort

_TREE_MAX_GENERATIONS = 50


class SqlAlchemyExportQueryPort(ExportQueryPort):
    """Archival read-side queries for the clan export use case."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def clan(self, clan_id: uuid.UUID) -> dict[str, Any]:
        result = await self._session.execute(
            text("SELECT * FROM clans WHERE id = :clan"), {"clan": clan_id}
        )
        row = result.mappings().one_or_none()
        return dict(row) if row is not None else {}

    async def persons(self, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text(
                "SELECT p.*, cm.role AS membership_role, cm.generation AS stored_generation, "
                "cm.is_founder, cm.branch_id, cm.id AS membership_id, cm.joined_at, "
                "cm.created_at AS membership_created_at, cm.updated_at AS membership_updated_at "
                "FROM persons p "
                "JOIN clan_memberships cm ON cm.person_id = p.id "
                "WHERE cm.clan_id = :clan"
            ),
            {"clan": clan_id},
        )
        return [dict(row) for row in result.mappings().all()]

    async def branches(self, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text("SELECT * FROM branches WHERE clan_id = :clan"), {"clan": clan_id}
        )
        return [dict(row) for row in result.mappings().all()]

    async def marriages(self, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text("SELECT * FROM marriages WHERE created_by_clan_id = :clan"), {"clan": clan_id}
        )
        return [dict(row) for row in result.mappings().all()]

    async def parent_child(self, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text("SELECT * FROM parent_child WHERE created_by_clan_id = :clan"),
            {"clan": clan_id},
        )
        return [dict(row) for row in result.mappings().all()]

    async def events(self, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text("SELECT * FROM events WHERE clan_id = :clan"), {"clan": clan_id}
        )
        return [dict(row) for row in result.mappings().all()]

    async def documents(self, clan_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            text("SELECT * FROM documents WHERE clan_id = :clan AND is_deleted = false"),
            {"clan": clan_id},
        )
        return [dict(row) for row in result.mappings().all()]

    async def generation_map(self, clan_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Graph-computed đời per person: for each clan founder, walk
        `get_family_tree_flat` and record `depth + 1` (thủy tổ = 1). The first
        founder processed wins for any person reachable from more than one
        founder (`dict.setdefault`) — founders are processed in a fixed,
        deterministic order (`joined_at` ascending, `person_id` tiebreak) so
        which founder "wins" a shared descendant does not depend on
        unspecified row order from Postgres."""
        founders_result = await self._session.execute(
            text(
                "SELECT cm.person_id FROM clan_memberships cm "
                "WHERE cm.clan_id = :clan AND cm.is_founder = true "
                "ORDER BY cm.joined_at NULLS LAST, cm.person_id"
            ),
            {"clan": clan_id},
        )
        founder_ids = [row.person_id for row in founders_result.all()]

        generations: dict[uuid.UUID, int] = {}
        for founder_id in founder_ids:
            tree_result = await self._session.execute(
                text(
                    "SELECT person_id, depth FROM public.get_family_tree_flat"
                    "(:founder, :clan, :max_gen)"
                ),
                {"founder": founder_id, "clan": clan_id, "max_gen": _TREE_MAX_GENERATIONS},
            )
            for row in tree_result.mappings().all():
                generations.setdefault(row["person_id"], row["depth"] + 1)
        return generations
