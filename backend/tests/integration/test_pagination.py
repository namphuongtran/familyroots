"""Cursor pagination: list endpoints page correctly and never leak the sentinel row.

The document/event list paths fetch limit+1 rows (paginate_query) to detect more
pages; previously they returned all of them with no cursor (over-returning one row,
no way to page). build_page now slices to limit and emits a cursor. This proves the
page size, has_more flag, and that the cursor fetches the remainder exactly once.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.application.document.handlers import DocumentQueryHandler
from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class _NoStorage:
    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        return path

    async def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        return storage_path

    async def delete(self, storage_path: str) -> bool:
        return True


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


async def test_document_list_paginates_with_cursor(async_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, actor = uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :sl)"),
            {"id": clan_id, "n": "C", "sl": f"c-{clan_id.hex[:8]}"},
        )
        # Seed 5 documents (created_at ordering is stable via the cursor's id tiebreak).
        for i in range(5):
            did = uuid.uuid4()
            await s.execute(
                sa.text(
                    "INSERT INTO documents (id, clan_id, title, document_type, storage_path, "
                    "created_by) VALUES (:id, :c, :t, 'photo', :sp, :cb)"
                ),
                {"id": did, "c": clan_id, "t": f"doc{i}", "sp": f"p/{did.hex}", "cb": actor},
            )
        await s.commit()

        handler = DocumentQueryHandler(SqlAlchemyDocumentRepository(s), _NoStorage())

        # First page of 2 → exactly 2 items, has_more, a cursor (no sentinel leak).
        page1, meta1 = await handler.list_documents(clan_id=clan_id, limit=2)
        assert len(page1) == 2
        assert meta1["has_more"] is True
        assert meta1["cursor"] is not None

        # Walk the cursor to exhaustion: 2 + 2 + 1 = 5, last page has_more False.
        page2, meta2 = await handler.list_documents(
            clan_id=clan_id, limit=2, cursor=meta1["cursor"]
        )
        page3, meta3 = await handler.list_documents(
            clan_id=clan_id, limit=2, cursor=meta2["cursor"]
        )
        assert len(page2) == 2
        assert len(page3) == 1
        assert meta3["has_more"] is False
        assert meta3["cursor"] is None

        # No id appears twice across pages, and all 5 are covered.
        seen = [d.id for d in (*page1, *page2, *page3)]
        assert len(set(seen)) == 5
