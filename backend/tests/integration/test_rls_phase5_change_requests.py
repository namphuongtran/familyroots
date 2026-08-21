"""RLS layer-2 Phase 5 (S-008, ADR-008): change_requests is clan-isolated at the DB.

Migration 030 enables the migration-027 clan-isolation policy on ``change_requests``. A
change request holds a *proposed* value for clan data before anyone approves it
(ADR-037), so a cross-clan read here exposes edits that were never accepted.

These prove enforcement through the runtime seam (``RlsSession`` + the ``app.clan_id``
ContextVar), and they assert at the database layer with naked SQL rather than through the
API, so an application-layer ``WHERE clan_id = …`` cannot stand in for the policy:

* isolation in BOTH directions — A cannot see B's row, and B cannot see A's;
* a write for the wrong clan is REJECTED (an error), never silently ignored — on INSERT
  and on an UPDATE that tries to move a row into another clan;
* no clan set → zero rows (fail closed);
* an ORM insert, whose ``RETURNING`` is the exact shape that broke ``persons`` under
  RLS (ADR-038), still succeeds here.
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
from app.models.change_request import ChangeRequest

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


async def _seed(conn: AsyncConnection, clan_id: uuid.UUID) -> uuid.UUID:
    """One clan holding one pending change request. Returns the request id."""
    await conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:10]}"},
    )
    cr_id = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO change_requests "
            "(id, clan_id, requester_id, action, resource_type, status) "
            "VALUES (:id, :c, :r, 'update', 'person', 'pending')"
        ),
        {"id": cr_id, "c": clan_id, "r": uuid.uuid4()},
    )
    return cr_id


async def _seed_two(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:  # privileged seeding, bypasses RLS
        cr_a = await _seed(conn, clan_a)
        cr_b = await _seed(conn, clan_b)
    return clan_a, clan_b, cr_a, cr_b


def _rls(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)


async def test_reads_are_scoped_to_the_active_clan_in_both_directions(
    engine: AsyncEngine,
) -> None:
    """Two-sided: under clan A the DB returns A's request and not B's, and under clan B
    the reverse. One direction alone would also pass on a policy that hides everything."""
    clan_a, clan_b, cr_a, cr_b = await _seed_two(engine)
    rls = _rls(engine)

    set_request_clan_id(clan_a)
    async with rls() as s:
        seen_by_a = set((await s.execute(sa.text("SELECT id FROM change_requests"))).scalars())
    assert cr_a in seen_by_a, seen_by_a
    assert cr_b not in seen_by_a, seen_by_a

    set_request_clan_id(clan_b)
    async with rls() as s:
        seen_by_b = set((await s.execute(sa.text("SELECT id FROM change_requests"))).scalars())
    assert cr_b in seen_by_b, seen_by_b
    assert cr_a not in seen_by_b, seen_by_b


async def test_targeted_read_of_the_other_clans_request_returns_nothing(
    engine: AsyncEngine,
) -> None:
    """Asking for the other clan's request BY ID — the shape a missed repository filter
    produces — returns no row, in both directions."""
    clan_a, clan_b, cr_a, cr_b = await _seed_two(engine)
    rls = _rls(engine)
    by_id = sa.text("SELECT count(*) FROM change_requests WHERE id = :id")

    set_request_clan_id(clan_a)
    async with rls() as s:
        assert await s.scalar(by_id, {"id": cr_b}) == 0
        assert await s.scalar(by_id, {"id": cr_a}) == 1

    set_request_clan_id(clan_b)
    async with rls() as s:
        assert await s.scalar(by_id, {"id": cr_a}) == 0
        assert await s.scalar(by_id, {"id": cr_b}) == 1


async def test_default_deny_when_no_clan(engine: AsyncEngine) -> None:
    """An unset GUC yields NULL, so the predicate is NULL and no row is visible."""
    await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(None)
    async with rls() as s:
        assert await s.scalar(sa.text("SELECT count(*) FROM change_requests")) == 0


async def test_with_check_rejects_a_cross_clan_insert(engine: AsyncEngine) -> None:
    """Under GUC = clan A, inserting a request labelled clan B RAISES. The write is
    rejected, not silently dropped — an ignored write would leave the caller believing
    the proposal was recorded."""
    clan_a, clan_b, _cr_a, _cr_b = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        with pytest.raises(sa.exc.DBAPIError) as ei:
            await s.execute(
                sa.text(
                    "INSERT INTO change_requests "
                    "(id, clan_id, requester_id, action, resource_type, status) "
                    "VALUES (:id, :c, :r, 'update', 'person', 'pending')"
                ),
                {"id": uuid.uuid4(), "c": clan_b, "r": uuid.uuid4()},
            )
            await s.flush()
        assert "row-level security" in str(ei.value).lower()


async def test_with_check_rejects_reassigning_a_request_to_another_clan(
    engine: AsyncEngine,
) -> None:
    """Under GUC = clan A, moving A's own request into clan B RAISES. USING admits the
    row for the update, WITH CHECK refuses the new one."""
    clan_a, clan_b, cr_a, _cr_b = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        with pytest.raises(sa.exc.DBAPIError) as ei:
            await s.execute(
                sa.text("UPDATE change_requests SET clan_id = :c WHERE id = :id"),
                {"c": clan_b, "id": cr_a},
            )
            await s.flush()
        assert "row-level security" in str(ei.value).lower()


async def test_update_of_the_other_clans_request_touches_no_row(engine: AsyncEngine) -> None:
    """The review path is an UPDATE. Under clan A, approving B's request matches nothing
    and B's row keeps its status — checked with a privileged read, so the policy that
    hid the row cannot also hide the damage."""
    clan_a, _clan_b, _cr_a, cr_b = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        updated = (
            (
                await s.execute(
                    sa.text(
                        "UPDATE change_requests SET status = 'approved' WHERE id = :id RETURNING id"
                    ),
                    {"id": cr_b},
                )
            )
            .scalars()
            .all()
        )
        assert list(updated) == []
        await s.commit()

    async with engine.connect() as conn:  # privileged: sees every clan
        status = await conn.scalar(
            sa.text("SELECT status FROM change_requests WHERE id = :id"), {"id": cr_b}
        )
    assert status == "pending"


async def test_orm_insert_with_returning_succeeds(engine: AsyncEngine) -> None:
    """The ADR-038 trap, checked for this table. Postgres matches an INSERT's RETURNING
    row against the SELECT policy, and SQLAlchemy appends RETURNING for server defaults
    (``created_at``). One permissive ALL policy means the same predicate that accepted
    the write also admits the returned row, so the real ORM write path works."""
    clan_a, _clan_b, _cr_a, _cr_b = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(clan_a)
    cr_id = uuid.uuid4()
    async with rls() as s:
        s.add(
            ChangeRequest(
                id=cr_id,
                clan_id=clan_a,
                requester_id=uuid.uuid4(),
                action="update",
                resource_type="person",
                status="pending",
            )
        )
        await s.commit()

    async with engine.connect() as conn:
        row = await conn.scalar(
            sa.text("SELECT created_at FROM change_requests WHERE id = :id"), {"id": cr_id}
        )
    assert row is not None
