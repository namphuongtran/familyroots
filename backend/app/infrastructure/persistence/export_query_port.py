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
from app.services.tree_builder import compute_generation_map


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
        """Graph-computed đời per person, delegating to the single đời
        authority (ADR-027, `compute_generation_map`): con theo đời cha, not
        BFS/min-depth. Pre-023 archives could have multiple live founders per
        clan, which this port handled with an ordered per-founder loop over
        `get_family_tree_flat` (`joined_at` ascending, `person_id` tiebreak,
        first founder processed wins a shared descendant via
        `dict.setdefault`) — that loop is retired because migration 023
        enforces exactly one live founder per clan (see
        `test_clan_export_json.py`'s single-founder determinism pin), so a
        single call to the shared authority now suffices and reads the SAME
        đời every other tree surface reads.

        `compute_generation_map` returns `{}` when the clan has no
        designated founder, and otherwise `{person_id: DoiEntry}` — adapted
        here to the `{person_id: generation}` shape this port's callers
        (`app/services/clan_export.py`, `app/services/gedcom_export.py`)
        expect."""
        doi_map = await compute_generation_map(self._session, clan_id)
        return {person_id: entry.generation for person_id, entry in doi_map.items()}

    async def release(self) -> None:
        """End the read transaction (ADR-028): a read-only session, so a
        rollback cleanly releases the pooled connection back to the pool
        before the caller starts a multi-round-trip external call (presign)."""
        await self._session.rollback()
