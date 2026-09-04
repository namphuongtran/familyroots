"""RLS layer-2 Phase 6 (ADR-008): clan_memberships is clan-isolated at the DB.

Migration 031 enables the migration-027 clan-isolation policy on ``clan_memberships``.
The row says "this person belongs to this clan", and carries the clan's own structural
claims about them (``generation``, ``is_founder``, ``branch_id``). A cross-clan read here
leaks the roster even when the ``persons`` row itself stays hidden.

These prove enforcement through the runtime seam (``RlsSession`` + the ``app.clan_id``
ContextVar), and they assert at the database layer with naked SQL rather than through the
API, so an application-layer ``WHERE clan_id = …`` cannot stand in for the policy:

* isolation in BOTH directions — A cannot see B's row, and B cannot see A's;
* a SHARED person (member of A and B) exposes one membership row per clan, and each clan
  sees only its own — the case a one-sided test would miss entirely;
* a write for the wrong clan is REJECTED (an error), never silently ignored — on INSERT
  and on an UPDATE that tries to move a row into another clan;
* no clan set → zero rows (fail closed);
* the ``persons`` SELECT policy (migration 029), whose predicate is an ``EXISTS`` over
  THIS table, still resolves now that this table is itself RLS-protected;
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
from app.models.clan_membership import ClanMembership

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


async def _person(conn: AsyncConnection, origin_clan: uuid.UUID) -> uuid.UUID:
    pid = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, created_by_clan_id, created_by) "
            "VALUES (:id, 'P', :c, :a)"
        ),
        {"id": pid, "c": origin_clan, "a": uuid.uuid4()},
    )
    return pid


async def _membership(conn: AsyncConnection, person_id: uuid.UUID, clan_id: uuid.UUID) -> uuid.UUID:
    mid = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO clan_memberships (id, person_id, clan_id, role) "
            "VALUES (:id, :p, :c, 'blood')"
        ),
        {"id": mid, "p": person_id, "c": clan_id},
    )
    return mid


async def _seed_two(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Two clans, each with its own person and that person's membership row.

    Returns ``(clan_a, clan_b, membership_a, membership_b)``. Seeding runs on the
    privileged connection, which bypasses RLS.
    """
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan_a)
        await _clan(conn, clan_b)
        m_a = await _membership(conn, await _person(conn, clan_a), clan_a)
        m_b = await _membership(conn, await _person(conn, clan_b), clan_b)
    return clan_a, clan_b, m_a, m_b


def _rls(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)


async def test_reads_are_scoped_to_the_active_clan_in_both_directions(
    engine: AsyncEngine,
) -> None:
    """Two-sided: under clan A the DB returns A's membership and not B's, and under clan B
    the reverse. One direction alone would also pass on a policy that hides everything."""
    clan_a, clan_b, m_a, m_b = await _seed_two(engine)
    rls = _rls(engine)

    set_request_clan_id(clan_a)
    async with rls() as s:
        seen_by_a = set((await s.execute(sa.text("SELECT id FROM clan_memberships"))).scalars())
    assert m_a in seen_by_a, seen_by_a
    assert m_b not in seen_by_a, seen_by_a

    set_request_clan_id(clan_b)
    async with rls() as s:
        seen_by_b = set((await s.execute(sa.text("SELECT id FROM clan_memberships"))).scalars())
    assert m_b in seen_by_b, seen_by_b
    assert m_a not in seen_by_b, seen_by_b


async def test_targeted_read_of_the_other_clans_membership_returns_nothing(
    engine: AsyncEngine,
) -> None:
    """Asking for the other clan's membership BY ID — the shape a missed repository filter
    produces — returns no row, in both directions."""
    clan_a, clan_b, m_a, m_b = await _seed_two(engine)
    rls = _rls(engine)
    by_id = sa.text("SELECT count(*) FROM clan_memberships WHERE id = :id")

    set_request_clan_id(clan_a)
    async with rls() as s:
        assert await s.scalar(by_id, {"id": m_b}) == 0
        assert await s.scalar(by_id, {"id": m_a}) == 1

    set_request_clan_id(clan_b)
    async with rls() as s:
        assert await s.scalar(by_id, {"id": m_a}) == 0
        assert await s.scalar(by_id, {"id": m_b}) == 1


async def test_shared_person_exposes_only_the_active_clans_membership_row(
    engine: AsyncEngine,
) -> None:
    """One person, member of A and B (đa tộc / a married-in spouse). Each clan sees its
    OWN membership row for that person and not the other clan's, in both directions.

    This is the case that distinguishes a working policy from an absent one most sharply:
    the ``persons`` row is legitimately visible to both clans, so only ``clan_memberships``
    can hide the fact that the other clan also claims them.
    """
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan_a)
        await _clan(conn, clan_b)
        shared = await _person(conn, clan_a)
        m_a = await _membership(conn, shared, clan_a)
        m_b = await _membership(conn, shared, clan_b)

    rls = _rls(engine)
    by_person = sa.text("SELECT id FROM clan_memberships WHERE person_id = :p")

    set_request_clan_id(clan_a)
    async with rls() as s:
        assert set((await s.execute(by_person, {"p": shared})).scalars()) == {m_a}

    set_request_clan_id(clan_b)
    async with rls() as s:
        assert set((await s.execute(by_person, {"p": shared})).scalars()) == {m_b}


async def test_default_deny_when_no_clan(engine: AsyncEngine) -> None:
    """An unset GUC yields NULL, so the predicate is NULL and no row is visible."""
    await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(None)
    async with rls() as s:
        assert await s.scalar(sa.text("SELECT count(*) FROM clan_memberships")) == 0


async def test_with_check_rejects_a_cross_clan_insert(engine: AsyncEngine) -> None:
    """Under GUC = clan A, inserting a membership labelled clan B RAISES. The write is
    rejected, not silently dropped — an ignored write would leave the caller believing the
    person had been added to the clan."""
    clan_a, clan_b, _m_a, _m_b = await _seed_two(engine)
    async with engine.begin() as conn:
        victim = await _person(conn, clan_b)

    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        with pytest.raises(sa.exc.DBAPIError) as ei:
            await s.execute(
                sa.text(
                    "INSERT INTO clan_memberships (id, person_id, clan_id, role) "
                    "VALUES (:id, :p, :c, 'blood')"
                ),
                {"id": uuid.uuid4(), "p": victim, "c": clan_b},
            )
            await s.flush()
        assert "row-level security" in str(ei.value).lower()


async def test_with_check_rejects_reassigning_a_membership_to_another_clan(
    engine: AsyncEngine,
) -> None:
    """Under GUC = clan A, moving A's own membership into clan B RAISES. USING admits the
    row for the update, WITH CHECK refuses the new one."""
    clan_a, clan_b, m_a, _m_b = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        with pytest.raises(sa.exc.DBAPIError) as ei:
            await s.execute(
                sa.text("UPDATE clan_memberships SET clan_id = :c WHERE id = :id"),
                {"c": clan_b, "id": m_a},
            )
            await s.flush()
        assert "row-level security" in str(ei.value).lower()


async def test_update_of_the_other_clans_membership_touches_no_row(engine: AsyncEngine) -> None:
    """Under clan A, promoting B's member to founder matches nothing and B's row is
    unchanged — checked with a privileged read, so the policy that hid the row cannot also
    hide the damage."""
    clan_a, _clan_b, _m_a, m_b = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        updated = (
            (
                await s.execute(
                    sa.text(
                        "UPDATE clan_memberships SET is_founder = true WHERE id = :id RETURNING id"
                    ),
                    {"id": m_b},
                )
            )
            .scalars()
            .all()
        )
        assert list(updated) == []
        await s.commit()

    async with engine.connect() as conn:  # privileged: sees every clan
        is_founder = await conn.scalar(
            sa.text("SELECT is_founder FROM clan_memberships WHERE id = :id"), {"id": m_b}
        )
    assert is_founder is False


async def test_delete_of_the_other_clans_membership_touches_no_row(engine: AsyncEngine) -> None:
    """Removing a person from a clan is a DELETE. Under clan A it cannot reach B's row —
    verified privileged, because a policy that hides the row also hides its absence."""
    clan_a, _clan_b, _m_a, m_b = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        await s.execute(sa.text("DELETE FROM clan_memberships WHERE id = :id"), {"id": m_b})
        await s.commit()

    async with engine.connect() as conn:
        still_there = await conn.scalar(
            sa.text("SELECT count(*) FROM clan_memberships WHERE id = :id"), {"id": m_b}
        )
    assert still_there == 1


async def test_persons_select_policy_still_resolves_through_this_table(
    engine: AsyncEngine,
) -> None:
    """Migration 029's ``persons_sel`` predicate is ``EXISTS (SELECT 1 FROM
    clan_memberships m WHERE m.person_id = persons.id AND m.clan_id = <GUC>)``.

    That subquery now runs against an RLS-protected table, so a policy whose predicate
    disagreed with 029's would silently make every person invisible — the tree would come
    back empty with no error anywhere. The two predicates are the same clan equality, so
    the composition is a no-op; this pins that.
    """
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan_a)
        await _clan(conn, clan_b)
        p_a = await _person(conn, clan_a)
        await _membership(conn, p_a, clan_a)

    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        assert p_a in set((await s.execute(sa.text("SELECT id FROM persons"))).scalars())
    set_request_clan_id(clan_b)
    async with rls() as s:
        assert p_a not in set((await s.execute(sa.text("SELECT id FROM persons"))).scalars())


async def test_orm_insert_with_returning_succeeds(engine: AsyncEngine) -> None:
    """The ADR-038 trap, checked for this table. Postgres matches an INSERT's RETURNING
    row against the SELECT policy, and SQLAlchemy appends RETURNING for server defaults
    (``created_at``/``updated_at``). One permissive ALL policy means the same predicate
    that accepted the write also admits the returned row, so ``save_with_membership``
    (``person_repository.py:224``) still works.
    """
    clan_a, _clan_b, _m_a, _m_b = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(clan_a)

    mid = uuid.uuid4()
    async with engine.begin() as conn:
        new_person = await _person(conn, clan_a)

    async with rls() as s:
        s.add(ClanMembership(id=mid, person_id=new_person, clan_id=clan_a, role="blood"))
        await s.commit()

    async with engine.connect() as conn:
        created_at = await conn.scalar(
            sa.text("SELECT created_at FROM clan_memberships WHERE id = :id"), {"id": mid}
        )
    assert created_at is not None
