"""Migration 018: indexes that back the actual query patterns.

Reviewed gaps, each matching a live query with no supporting index:
- persons list keysets on (full_name, id) but persons had only a GIN trigram
  on f_unaccent(full_name) — GIN can't serve ORDER BY, so every page sorted
  the clan's whole membership join.
- documents/events cursor lists order by (created_at, id) filtered by clan_id
  but had only single-column clan indexes.
- identity_claims list_user_claims filters user_id over any status; the only
  user_id index was partial WHERE status='PENDING'.
- the document purge job scans is_deleted = true AND deleted_at < cutoff; the
  only is_deleted index is partial on the OPPOSITE half (= false).
- tree CTEs join parent_child on (parent_id, created_by_clan_id, is_deleted).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_EXPECTED = {
    "persons": "idx_persons_fullname_keyset",
    "documents": "idx_documents_clan_created",
    "events": "idx_events_clan_created",
    "identity_claims": "idx_identity_claims_user_created",
    "parent_child": "idx_parent_child_parent_clan_live",
}
_PURGE = ("documents", "idx_documents_purge_due")


@pytest.fixture()
async def session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _index_names(session: AsyncSession, table: str) -> set[str]:
    rows = await session.execute(
        sa.text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": table}
    )
    return {r.indexname for r in rows}


async def test_query_support_indexes_exist(session: AsyncSession) -> None:
    for table, index in [*_EXPECTED.items(), _PURGE]:
        names = await _index_names(session, table)
        assert index in names, f"{table} missing {index}; has {sorted(names)}"


async def test_purge_index_covers_the_deleted_half(session: AsyncSession) -> None:
    row = (
        await session.execute(
            sa.text("SELECT indexdef FROM pg_indexes WHERE indexname = 'idx_documents_purge_due'")
        )
    ).first()
    assert row is not None
    assert "is_deleted = true" in row.indexdef.lower()
