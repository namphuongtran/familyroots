"""Soft-deleted persons must not surface through spouse decorations.

Two joins fetched spouse persons with no `p.is_deleted = false` predicate,
while every sibling helper filters it: the tree builder's spouse query
(spouses[] on every tree node) and the timeline's marriage join. A
soft-deleted wife disappeared from search and tree nodes but kept rendering
in both places. Two-sided: the live spouse stays visible.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence.person_query_port import SqlAlchemyPersonQueryPort
from app.services.tree_builder import build_descendants_tree

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed(s: AsyncSession) -> dict[str, uuid.UUID]:
    """Husband (member) with one live wife and one soft-deleted wife (đa thê)."""
    creator = uuid.uuid4()
    clan_id = uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:8]}"},
    )
    ids: dict[str, uuid.UUID] = {"clan_id": clan_id}
    for key, name, gender, deleted in (
        ("husband", "Chồng", "male", False),
        ("wife_live", "Vợ Cả", "female", False),
        ("wife_deleted", "Vợ Đã Xoá", "female", True),
    ):
        pid = uuid.uuid4()
        await s.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by, "
                " is_deleted, deleted_at) "
                "VALUES (:id, :n, :g, :c, :cb, :d, CASE WHEN :d THEN now() END)"
            ),
            {"id": pid, "n": name, "g": gender, "c": clan_id, "cb": creator, "d": deleted},
        )
        ids[key] = pid
    await s.execute(
        sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
        {"p": ids["husband"], "c": clan_id},
    )
    for order, wife in ((1, "wife_live"), (2, "wife_deleted")):
        await s.execute(
            sa.text(
                "INSERT INTO marriages (id, person1_id, person2_id, status, spouse_order, "
                " marriage_date, created_by_clan_id, created_by) "
                "VALUES (:id, :p1, :p2, 'married', :o, '1980-01-01', :c, :cb)"
            ),
            {
                "id": uuid.uuid4(),
                "p1": ids["husband"],
                "p2": ids[wife],
                "o": order,
                "c": clan_id,
                "cb": creator,
            },
        )
    await s.commit()
    return ids


async def test_tree_spouses_exclude_soft_deleted(async_session: AsyncSession) -> None:
    ids = await _seed(async_session)
    tree = await build_descendants_tree(async_session, ids["husband"], ids["clan_id"])
    spouse_ids = {sp["id"] for sp in tree["spouses"]}
    assert str(ids["wife_live"]) in spouse_ids  # negative control
    assert str(ids["wife_deleted"]) not in spouse_ids


async def test_timeline_marriages_exclude_soft_deleted_spouse(
    async_session: AsyncSession,
) -> None:
    ids = await _seed(async_session)
    port = SqlAlchemyPersonQueryPort(async_session)
    timeline = await port.get_timeline(ids["clan_id"], ids["husband"])
    marriage_partners = {
        e["related_person_name"] for e in timeline if e["event_type"] == "marriage"
    }
    assert "Vợ Cả" in marriage_partners  # negative control
    assert "Vợ Đã Xoá" not in marriage_partners
