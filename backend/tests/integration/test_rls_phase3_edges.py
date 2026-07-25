"""RLS layer-2 Phase 3 (SP-3, ADR-008): parent_child + marriages are clan-isolated,
AND the tree SQL functions + the parent_child BEFORE trigger still work under the seam.

Migration 028 enables the clan-isolation policy (created_by_clan_id = app.clan_id) on the
tree edges. The subtle risk vs events/branches: the SECURITY-INVOKER tree functions
(find_relationship_path, get_ancestors_flat) and the parent_child BEFORE-ROW trigger run
under the request role with the GUC set, so their edge queries are RLS-filtered. Because
they are clan-scoped by p_clan_id / created_by_clan_id = the request's clan = the GUC, the
predicate is redundant → results unchanged. These tests prove reads are scoped, the tree
functions return correctly under the seam, and a write survives the trigger + WITH CHECK.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import RlsSession
from app.core.rls import set_request_clan_id

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.fixture(autouse=True)
def _reset_clan_context() -> Generator[None]:
    set_request_clan_id(None)
    yield
    set_request_clan_id(None)


async def _person(conn: AsyncConnection, clan_id: uuid.UUID, actor: uuid.UUID) -> uuid.UUID:
    pid = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, created_by_clan_id, created_by) "
            "VALUES (:id, 'P', :c, :a)"
        ),
        {"id": pid, "c": clan_id, "a": actor},
    )
    # A clan_memberships row so the person is visible under persons-RLS (Phase 4) — every
    # person in a clan's tree is a member of it.
    await conn.execute(
        sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
        {"p": pid, "c": clan_id},
    )
    return pid


async def _edge(
    conn: AsyncConnection, parent: uuid.UUID, child: uuid.UUID, clan_id: uuid.UUID, actor: uuid.UUID
) -> uuid.UUID:
    eid = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO parent_child (id, parent_id, child_id, created_by_clan_id, "
            "relationship_type, created_by) VALUES (:id, :p, :c, :cl, 'biological', :a)"
        ),
        {"id": eid, "p": parent, "c": child, "cl": clan_id, "a": actor},
    )
    return eid


async def _seed_clan_graph(conn: AsyncConnection, clan_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """gpa → dad → kid (two edges) + a gpa/gma marriage, all in one clan."""
    await conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:10]}"},
    )
    actor = uuid.uuid4()
    gpa, gma, dad, kid = [await _person(conn, clan_id, actor) for _ in range(4)]
    e1 = await _edge(conn, gpa, dad, clan_id, actor)
    await _edge(conn, dad, kid, clan_id, actor)
    marriage_id = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO marriages (id, person1_id, person2_id, created_by_clan_id, "
            "status, created_by) VALUES (:id, :p1, :p2, :cl, 'married', :a)"
        ),
        {"id": marriage_id, "p1": gpa, "p2": gma, "cl": clan_id, "a": actor},
    )
    return {"gpa": gpa, "dad": dad, "kid": kid, "edge": e1, "marriage": marriage_id, "actor": actor}


async def _seed_two(
    engine: AsyncEngine,
) -> tuple[uuid.UUID, uuid.UUID, dict[str, uuid.UUID], dict[str, uuid.UUID]]:
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        a = await _seed_clan_graph(conn, clan_a)
        b = await _seed_clan_graph(conn, clan_b)
    return clan_a, clan_b, a, b


@pytest.mark.parametrize(("table", "key"), [("parent_child", "edge"), ("marriages", "marriage")])
async def test_edges_scoped_to_active_clan(engine: AsyncEngine, table: str, key: str) -> None:
    clan_a, _clan_b, a, b = await _seed_two(engine)
    rls = async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)
    set_request_clan_id(clan_a)
    async with rls() as s:
        ids = set((await s.execute(sa.text(f"SELECT id FROM {table}"))).scalars().all())
    assert a[key] in ids and b[key] not in ids, (table, ids)


async def test_default_deny_when_no_clan(engine: AsyncEngine) -> None:
    await _seed_two(engine)
    rls = async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)
    set_request_clan_id(None)
    async with rls() as s:
        assert await s.scalar(sa.text("SELECT count(*) FROM parent_child")) == 0
        assert await s.scalar(sa.text("SELECT count(*) FROM marriages")) == 0


async def test_with_check_rejects_cross_clan_marriage_write(engine: AsyncEngine) -> None:
    clan_a, clan_b, _a, b = await _seed_two(engine)
    rls = async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)
    set_request_clan_id(clan_a)
    async with rls() as s:
        with pytest.raises(sa.exc.DBAPIError) as ei:
            await s.execute(
                sa.text(
                    "INSERT INTO marriages (id, person1_id, person2_id, created_by_clan_id, "
                    "status, created_by) VALUES (:id, :p1, :p2, :cl, 'married', :a)"
                ),
                {"id": uuid.uuid4(), "p1": b["gpa"], "p2": b["dad"], "cl": clan_b, "a": b["actor"]},
            )
            await s.flush()
        assert "row-level security" in str(ei.value).lower()


async def test_tree_functions_work_under_the_seam(engine: AsyncEngine) -> None:
    """find_relationship_path + get_ancestors_flat (SECURITY INVOKER) must return the
    clan's graph under the request role with the GUC set — RLS on the edges must not
    break or empty them (the predicate is redundant with the function's p_clan_id filter)."""
    clan_a, _clan_b, a, _b = await _seed_two(engine)
    rls = async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)
    set_request_clan_id(clan_a)
    async with rls() as s:
        path = (
            (
                await s.execute(
                    sa.text(
                        "SELECT person_id FROM public.find_relationship_path(:f, :t, :c) ORDER BY step"
                    ),
                    {"f": a["gpa"], "t": a["kid"], "c": clan_a},
                )
            )
            .scalars()
            .all()
        )
        assert list(path) == [a["gpa"], a["dad"], a["kid"]], path

        ancestors = set(
            (
                await s.execute(
                    sa.text("SELECT person_id FROM public.get_ancestors_flat(:p, :c, 10)"),
                    {"p": a["kid"], "c": clan_a},
                )
            )
            .scalars()
            .all()
        )
        assert ancestors == {a["gpa"], a["dad"], a["kid"]}, ancestors


async def test_edge_write_survives_before_trigger_under_the_seam(engine: AsyncEngine) -> None:
    """A parent_child INSERT under the request role fires the SECURITY-INVOKER BEFORE
    trigger (advisory lock + bio-cap/cycle checks, whose edge queries are RLS-filtered by
    the GUC) and must succeed + satisfy WITH CHECK (created_by_clan_id = GUC)."""
    clan_a, _clan_b, _a, _b = await _seed_two(engine)
    # Two fresh clan-A persons to link (privileged seed).
    async with engine.begin() as conn:
        actor = uuid.uuid4()
        parent = await _person(conn, clan_a, actor)
        child = await _person(conn, clan_a, actor)

    rls = async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)
    set_request_clan_id(clan_a)
    edge_id = uuid.uuid4()
    async with rls() as s:
        await s.execute(
            sa.text(
                "INSERT INTO parent_child (id, parent_id, child_id, created_by_clan_id, "
                "relationship_type, created_by) VALUES (:id, :p, :c, :cl, 'biological', :a)"
            ),
            {"id": edge_id, "p": parent, "c": child, "cl": clan_a, "a": actor},
        )
        await s.commit()
        found = await s.scalar(
            sa.text("SELECT id FROM parent_child WHERE id = :id"), {"id": edge_id}
        )
    assert found == edge_id
