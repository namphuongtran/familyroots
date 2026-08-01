"""Track-B B3 (perf net): the clan person-list enumerates the clan via an index.

GET /persons lists a clan's members, cursor-paginated by (full_name, id). The query joins
clan_memberships filtered by clan_id; the load-bearing scaling property is that the clan
scope is reached through a clan_memberships clan_id index (``idx_clan_memberships_clan``),
so enumerating a clan's members costs O(that clan's members), not a sequential scan of
every clan's memberships. At tiny test-data volumes the planner legitimately prefers a
seq scan (cheaper than index probes on a few hundred rows), so — like the persons-RLS
index perf test — we force ``enable_seqscan = off`` and assert the clan_id index path
EXISTS and is used (a regression that dropped that index would seq-scan clan_memberships
even with seqscan off, failing here). The persons side of the join is planner/scale
dependent (a bitmap/seq scan at test volume, a PK nested-loop at production volume) and is
deliberately not over-asserted.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


async def _clan(conn: AsyncConnection, clan_id: uuid.UUID) -> None:
    await conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:8]}"},
    )


async def _seed_clan_members(conn: AsyncConnection, clan_id: uuid.UUID, n: int) -> None:
    """n persons in clan_id, each a member (bulk, so the planner has real stats)."""
    await _clan(conn, clan_id)
    await conn.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, created_by_clan_id, created_by) "
            "SELECT gen_random_uuid(), 'P'||g, :c, gen_random_uuid() "
            "FROM generate_series(1, :n) g"
        ),
        {"c": clan_id, "n": n},
    )
    await conn.execute(
        sa.text(
            "INSERT INTO clan_memberships (person_id, clan_id) "
            "SELECT id, created_by_clan_id FROM persons WHERE created_by_clan_id = :c"
        ),
        {"c": clan_id},
    )


_LIST_SQL = """
EXPLAIN
SELECT p.* FROM persons p
JOIN clan_memberships cm ON cm.person_id = p.id
WHERE cm.clan_id = :c AND p.is_deleted = false
ORDER BY p.full_name, p.id
LIMIT 51
"""


async def test_person_list_clan_scope_is_index_backed(engine: AsyncEngine) -> None:
    target = uuid.uuid4()
    async with engine.begin() as conn:
        # The target clan is a SMALL slice; two other clans hold most persons, so a
        # seq scan on persons would be the wrong (non-scaling) plan for this clan.
        await _seed_clan_members(conn, target, 40)
        await _seed_clan_members(conn, uuid.uuid4(), 400)
        await _seed_clan_members(conn, uuid.uuid4(), 400)
    async with engine.connect() as conn:
        await conn.execute(sa.text("ANALYZE persons"))
        await conn.execute(sa.text("ANALYZE clan_memberships"))
        # Force the scale-relevant plan: prove an index path exists (at prod volumes the
        # planner picks it on cost; at test volumes a seq scan is cheaper, so we force it).
        await conn.execute(sa.text("SET enable_seqscan = off"))
        rows = (await conn.execute(sa.text(_LIST_SQL), {"c": target})).scalars().all()
    plan = "\n".join(rows)

    # Clan scope is reached via a clan_memberships clan_id index — idx_clan_memberships_clan
    # or the clan_id-prefixed idx_clan_memberships_clan_generation (the substring matches
    # both) — never a seq scan on clan_memberships. That is what keeps enumerating a clan's
    # members O(that clan), independent of how many other clans exist.
    assert "idx_clan_memberships_clan" in plan, plan
    assert "Seq Scan on clan_memberships" not in plan, plan
