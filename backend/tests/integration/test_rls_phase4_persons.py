"""RLS layer-2 Phase 4 (SP-3, ADR-008): persons are membership-isolated at the DB, with
per-command policies + cross-clan readers routed to the privileged system session.

persons is M:N. Migration 029 uses per-command policies: SELECT/UPDATE/DELETE require the
active clan's membership; INSERT WITH CHECK created_by_clan_id = GUC; UPDATE WITH CHECK
permissive. These prove read isolation, shared-person visibility, that create /
shared-person edit survive (the WITH CHECK traps are avoided), the tree is not truncated,
default-deny, and that the two cross-clan readers (claim repo, platform metrics) still
resolve persons via the system session (bypass).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import RlsSession
from app.core.rls import set_request_clan_id
from app.infrastructure.persistence.claim_repository import SqlAlchemyClaimRepository
from app.infrastructure.persistence.platform_admin_query_port import (
    SqlAlchemyPlatformAdminQueryPort,
)

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


async def _clan(conn: AsyncConnection, clan_id: uuid.UUID) -> None:
    await conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:10]}"},
    )


async def _person(
    conn: AsyncConnection, origin_clan: uuid.UUID, member_of: list[uuid.UUID]
) -> uuid.UUID:
    """A person with origin=origin_clan and a clan_memberships row for each of member_of."""
    pid, actor = uuid.uuid4(), uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, created_by_clan_id, created_by) "
            "VALUES (:id, 'P', :c, :a)"
        ),
        {"id": pid, "c": origin_clan, "a": actor},
    )
    for cid in member_of:
        await conn.execute(
            sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
            {"p": pid, "c": cid},
        )
    return pid


def _rls(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)


async def test_person_visible_only_to_member_clan(engine: AsyncEngine) -> None:
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan_a)
        await _clan(conn, clan_b)
        p_a = await _person(conn, clan_a, [clan_a])  # member of A only

    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        assert p_a in set((await s.execute(sa.text("SELECT id FROM persons"))).scalars().all())
    set_request_clan_id(clan_b)
    async with rls() as s:
        assert p_a not in set((await s.execute(sa.text("SELECT id FROM persons"))).scalars().all())


async def test_shared_person_visible_to_both_clans(engine: AsyncEngine) -> None:
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan_a)
        await _clan(conn, clan_b)
        shared = await _person(conn, clan_a, [clan_a, clan_b])  # origin A, member of A+B

    rls = _rls(engine)
    for clan in (clan_a, clan_b):
        set_request_clan_id(clan)
        async with rls() as s:
            ids = set((await s.execute(sa.text("SELECT id FROM persons"))).scalars().all())
        assert shared in ids, clan


async def test_create_person_with_membership_under_seam(engine: AsyncEngine) -> None:
    """save_with_membership order (person row THEN membership row) survives INSERT
    WITH CHECK (created_by_clan_id = GUC), and the person is then visible as a member."""
    clan_a = uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan_a)

    rls = _rls(engine)
    set_request_clan_id(clan_a)
    pid, actor = uuid.uuid4(), uuid.uuid4()
    async with rls() as s:
        await s.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, created_by_clan_id, created_by) "
                "VALUES (:id, 'New', :c, :a)"
            ),
            {"id": pid, "c": clan_a, "a": actor},
        )
        await s.execute(
            sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
            {"p": pid, "c": clan_a},
        )
        await s.commit()
        assert pid in set((await s.execute(sa.text("SELECT id FROM persons"))).scalars().all())


async def test_shared_person_edit_by_non_origin_member_under_seam(engine: AsyncEngine) -> None:
    """A person whose origin (created_by_clan_id) is clan A but who is a member of clan B
    can be UPDATEd under GUC = B — the permissive UPDATE WITH CHECK avoids the
    created_by_clan_id=GUC trap that would reject a legitimate shared-person edit."""
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan_a)
        await _clan(conn, clan_b)
        shared = await _person(conn, clan_a, [clan_a, clan_b])  # origin A, member of B too

    rls = _rls(engine)
    set_request_clan_id(clan_b)
    async with rls() as s:
        await s.execute(
            sa.text("UPDATE persons SET full_name = 'Edited by B' WHERE id = :id"), {"id": shared}
        )
        await s.commit()
        name = await s.scalar(
            sa.text("SELECT full_name FROM persons WHERE id = :id"), {"id": shared}
        )
    assert name == "Edited by B"


async def test_default_deny_persons_when_no_clan(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        c = uuid.uuid4()
        await _clan(conn, c)
        await _person(conn, c, [c])
    rls = _rls(engine)
    set_request_clan_id(None)
    async with rls() as s:
        assert await s.scalar(sa.text("SELECT count(*) FROM persons")) == 0


async def test_tree_not_truncated_under_persons_rls(engine: AsyncEngine) -> None:
    """find_relationship_path JOINs persons; under persons-RLS every node is a member of
    the clan, so the full path still returns (no truncation)."""
    clan_a = uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan_a)
        gpa = await _person(conn, clan_a, [clan_a])
        dad = await _person(conn, clan_a, [clan_a])
        kid = await _person(conn, clan_a, [clan_a])
        actor = uuid.uuid4()
        for parent, child in ((gpa, dad), (dad, kid)):
            await conn.execute(
                sa.text(
                    "INSERT INTO parent_child (id, parent_id, child_id, created_by_clan_id, "
                    "relationship_type, created_by) VALUES (:id, :p, :c, :cl, 'biological', :a)"
                ),
                {"id": uuid.uuid4(), "p": parent, "c": child, "cl": clan_a, "a": actor},
            )

    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        path = (
            (
                await s.execute(
                    sa.text(
                        "SELECT person_id FROM public.find_relationship_path(:f, :t, :c) "
                        "ORDER BY step"
                    ),
                    {"f": gpa, "t": kid, "c": clan_a},
                )
            )
            .scalars()
            .all()
        )
    assert list(path) == [gpa, dad, kid], path


async def test_claim_repo_resolves_person_cross_clan_on_system_session(
    engine: AsyncEngine,
) -> None:
    """The claim flow runs on the SYSTEM session (bypass), so get_live_person resolves a
    person by global id even under persons-RLS with no clan context (would be None on the
    request/RLS session)."""
    clan_a = uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan_a)
        p_a = await _person(conn, clan_a, [clan_a])

    system = async_sessionmaker(engine, expire_on_commit=False)  # default = system, no seam
    set_request_clan_id(None)  # claimant has no clan context
    async with system() as s:
        found = await SqlAlchemyClaimRepository(s).get_live_person(p_a)
    assert found is not None and found.id == p_a


async def test_platform_metrics_count_persons_across_clans_on_system_session(
    engine: AsyncEngine,
) -> None:
    """Platform metrics run on the system session, so total_members counts persons across
    all clans (would be 0 under persons-RLS with no GUC)."""
    async with engine.begin() as conn:
        for _ in range(2):
            c = uuid.uuid4()
            await _clan(conn, c)
            await _person(conn, c, [c])

    system = async_sessionmaker(engine, expire_on_commit=False)
    set_request_clan_id(None)
    async with system() as s:
        metrics = await SqlAlchemyPlatformAdminQueryPort(s).get_metrics()
    assert metrics.total_members >= 2


async def test_persons_rls_membership_subquery_is_index_backed(engine: AsyncEngine) -> None:
    """Perf (ADR-008): the per-row membership EXISTS in the persons SELECT policy must use
    a clan_memberships index, not a seq scan. Seed enough rows + ANALYZE so the planner
    has real stats (mirrors the trigram-index test)."""
    clan_a = uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan_a)
        # ~300 members so the planner prefers the index for the EXISTS.
        await conn.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, created_by_clan_id, created_by) "
                "SELECT gen_random_uuid(), 'P'||g, :c, gen_random_uuid() "
                "FROM generate_series(1, 300) g"
            ),
            {"c": clan_a},
        )
        await conn.execute(
            sa.text(
                "INSERT INTO clan_memberships (person_id, clan_id) "
                "SELECT id, created_by_clan_id FROM persons WHERE created_by_clan_id = :c"
            ),
            {"c": clan_a},
        )
    async with engine.connect() as conn:
        await conn.execute(sa.text("ANALYZE persons"))
        await conn.execute(sa.text("ANALYZE clan_memberships"))

    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        await s.execute(sa.text("SET LOCAL enable_seqscan = off"))
        rows = (await s.execute(sa.text("EXPLAIN SELECT id FROM persons"))).scalars().all()
        plan = "\n".join(rows)
    # The membership EXISTS must be served by a clan_memberships index.
    assert "clan_memberships" in plan and "Index" in plan, plan
    assert "Seq Scan on clan_memberships" not in plan, plan
