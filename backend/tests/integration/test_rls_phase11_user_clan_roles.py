"""RLS layer-2 Phase 11 (S-052, ADR-050): ``user_clan_roles`` is HALF covered, on purpose.

Migration 036 does not give this table the migration-027 template. It gives it four
per-command policies:

===========  ==========================================================================
``SELECT``   ``USING (true)`` — permissive by decision. The authorization gate itself
             (``app/core/security.py:249-254``) reads this table before any clan is
             chosen, and ``GET /me/clans`` is cross-clan by design.
``INSERT``   ``WITH CHECK (true)`` — permissive by decision. ``POST /auth/onboard``
             writes the caller's own membership with no clan selected.
``UPDATE``   clan-keyed on both halves. **This is what the migration is for.**
``DELETE``   clan-keyed. Same.
===========  ==========================================================================

**Why the write half is the half worth having on this table.** Measured 2026-08-22: the
only UPDATE/DELETE statements against ``user_clan_roles`` on a request session are the four
in ``app/infrastructure/persistence/clan_repository.py`` — ``approve_if_pending``
(``:148-154``), ``delete_role_by_id`` (``:182-187``), ``delete_if_pending`` (``:199-204``)
and ``change_role_if`` (``:217-223``) — and **every one of them is keyed on the primary key
alone, with no ``clan_id`` predicate**. Their clan safety rests on ``ucr_id`` having come
from the clan-filtered ``get_user_clan_role`` (``:31-39``) a few lines earlier in
``app/application/clan/handlers.py`` (``:59``, ``:97``, ``:130``, ``:172``). That is a
read-then-write pair, not a filter. A record leaks by being read; a capability leaks by
being written, and this table is a capability.

Every assertion below runs through the runtime seam (``RlsSession`` plus the
``app.clan_id`` ContextVar) and is made with naked SQL at the database layer, so no
application-layer ``WHERE clan_id = …`` can stand in for the policy. Every denial ends with
a **privileged** read proving the row was really there and really unchanged — otherwise a
migration that dropped the rows and a policy that works are one reading.

The deliberate hole is asserted too, in
``test_reads_are_deliberately_permissive_and_this_is_the_decided_absence``. If someone
makes SELECT clan-keyed without first moving the clan-less readers, that test fails and
names ADR-050. An absence nobody pinned is an absence nobody notices.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
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


async def _clan(conn: AsyncConnection, clan_id: uuid.UUID) -> None:
    await conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:10]}"},
    )


async def _role(
    conn: AsyncConnection, clan_id: uuid.UUID, *, role: str, approved: bool
) -> uuid.UUID:
    user_id = uuid.uuid4()
    await conn.execute(
        sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:i, :e, 'u')"),
        {"i": user_id, "e": f"{user_id.hex[:12]}@example.com"},
    )
    ucr_id = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO user_clan_roles (id, clan_id, user_id, role, is_approved) "
            "VALUES (:id, :c, :u, :r, :a)"
        ),
        {"id": ucr_id, "c": clan_id, "u": user_id, "r": role, "a": approved},
    )
    return ucr_id


async def _seed_two(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Two clans, each with one PENDING viewer membership. Seeding runs privileged.

    Pending rather than approved because ``approve_if_pending`` and ``delete_if_pending``
    — two of the four statements this policy guards — only match a pending row, so the
    fixture has to be in the state the real statements target.

    Returns ``(clan_a, clan_b, ucr_a, ucr_b)``.
    """
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan_a)
        await _clan(conn, clan_b)
        ucr_a = await _role(conn, clan_a, role="viewer", approved=False)
        ucr_b = await _role(conn, clan_b, role="viewer", approved=False)
    return clan_a, clan_b, ucr_a, ucr_b


def _rls(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine, sync_session_class=RlsSession, expire_on_commit=False, class_=AsyncSession
    )


async def _privileged_row(engine: AsyncEngine, ucr_id: uuid.UUID) -> tuple[str, bool] | None:
    """Read one role row on a privileged (RLS-bypassing) connection.

    Every denial below ends here. Without it, "the UPDATE matched nothing" and "the row
    was never written" are the same reading.
    """
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                sa.text("SELECT role, is_approved FROM user_clan_roles WHERE id = :i"),
                {"i": ucr_id},
            )
        ).first()
    return (row.role, row.is_approved) if row else None


# ── UPDATE: the approve / change-role half ──────────────────────────────────────


async def test_update_cannot_reach_another_clans_role_row(engine: AsyncEngine) -> None:
    """Clan A, selected, runs the exact statement ``change_role_if`` runs, aimed at clan
    B's row id. It must match zero rows, and B's row must be untouched.

    This is the escalation this migration exists to stop: a ``ucr_id`` that reached the
    statement from anywhere other than the clan-filtered read would otherwise grant admin
    in a clan the caller has nothing to do with.
    """
    clan_a, _clan_b, _ucr_a, ucr_b = await _seed_two(engine)
    set_request_clan_id(clan_a)
    async with _rls(engine)() as s:
        result = await s.execute(
            sa.text(
                "UPDATE user_clan_roles SET role = 'admin' "
                "WHERE id = :i AND role = 'viewer' RETURNING id"
            ),
            {"i": ucr_b},
        )
        assert result.first() is None
        await s.commit()
    assert await _privileged_row(engine, ucr_b) == ("viewer", False)


async def test_update_does_reach_its_own_clans_role_row(engine: AsyncEngine) -> None:
    """The other direction of the same statement, so the denial above is isolation and not
    a policy that simply blocks everything."""
    clan_a, _clan_b, ucr_a, _ucr_b = await _seed_two(engine)
    set_request_clan_id(clan_a)
    async with _rls(engine)() as s:
        result = await s.execute(
            sa.text(
                "UPDATE user_clan_roles SET role = 'admin' "
                "WHERE id = :i AND role = 'viewer' RETURNING id"
            ),
            {"i": ucr_a},
        )
        assert result.scalar_one() == ucr_a
        await s.commit()
    assert await _privileged_row(engine, ucr_a) == ("admin", False)


async def test_update_cannot_move_a_role_row_into_another_clan(engine: AsyncEngine) -> None:
    """The ``WITH CHECK`` half. Clan A may reach its own row, and may not rewrite that
    row's ``clan_id`` to clan B — which would hand B a member it never approved."""
    clan_a, clan_b, ucr_a, _ucr_b = await _seed_two(engine)
    set_request_clan_id(clan_a)
    async with _rls(engine)() as s:
        with pytest.raises(ProgrammingError, match="row-level security"):
            await s.execute(
                sa.text("UPDATE user_clan_roles SET clan_id = :b WHERE id = :i"),
                {"b": clan_b, "i": ucr_a},
            )
        await s.rollback()
    assert await _privileged_row(engine, ucr_a) == ("viewer", False)


async def test_approve_shaped_update_is_denied_when_no_clan_is_selected(
    engine: AsyncEngine,
) -> None:
    """Fail closed. With no clan selected the predicate is NULL, so the statement
    ``approve_if_pending`` runs matches nothing at all — in either clan."""
    _clan_a, _clan_b, ucr_a, ucr_b = await _seed_two(engine)
    set_request_clan_id(None)
    async with _rls(engine)() as s:
        for ucr_id in (ucr_a, ucr_b):
            result = await s.execute(
                sa.text(
                    "UPDATE user_clan_roles SET is_approved = true "
                    "WHERE id = :i AND is_approved = false RETURNING id"
                ),
                {"i": ucr_id},
            )
            assert result.first() is None
        await s.commit()
    assert await _privileged_row(engine, ucr_a) == ("viewer", False)
    assert await _privileged_row(engine, ucr_b) == ("viewer", False)


# ── DELETE: the reject / remove half ────────────────────────────────────────────


async def test_delete_cannot_reach_another_clans_role_row(engine: AsyncEngine) -> None:
    """The statement ``delete_role_by_id`` runs, aimed across the boundary. It must match
    nothing, and B's member must still be a member."""
    clan_a, _clan_b, _ucr_a, ucr_b = await _seed_two(engine)
    set_request_clan_id(clan_a)
    async with _rls(engine)() as s:
        result = await s.execute(
            sa.text("DELETE FROM user_clan_roles WHERE id = :i RETURNING id"), {"i": ucr_b}
        )
        assert result.first() is None
        await s.commit()
    assert await _privileged_row(engine, ucr_b) == ("viewer", False)


async def test_delete_does_reach_its_own_clans_role_row(engine: AsyncEngine) -> None:
    """The positive side, so the denial above is not a policy that blocks every delete."""
    clan_a, _clan_b, ucr_a, _ucr_b = await _seed_two(engine)
    set_request_clan_id(clan_a)
    async with _rls(engine)() as s:
        result = await s.execute(
            sa.text("DELETE FROM user_clan_roles WHERE id = :i RETURNING id"), {"i": ucr_a}
        )
        assert result.scalar_one() == ucr_a
        await s.commit()
    assert await _privileged_row(engine, ucr_a) is None


async def test_delete_is_denied_when_no_clan_is_selected(engine: AsyncEngine) -> None:
    """Fail closed on DELETE too, with the rows proven still present afterwards."""
    _clan_a, _clan_b, ucr_a, ucr_b = await _seed_two(engine)
    set_request_clan_id(None)
    async with _rls(engine)() as s:
        result = await s.execute(
            sa.text("DELETE FROM user_clan_roles WHERE id IN (:a, :b) RETURNING id"),
            {"a": ucr_a, "b": ucr_b},
        )
        assert result.first() is None
        await s.commit()
    assert await _privileged_row(engine, ucr_a) == ("viewer", False)
    assert await _privileged_row(engine, ucr_b) == ("viewer", False)


# ── The two deliberate holes, pinned so nobody closes one by accident ───────────


async def test_reads_are_deliberately_permissive_and_this_is_the_decided_absence(
    engine: AsyncEngine,
) -> None:
    """``user_clan_roles_sel`` is ``USING (true)``, so clan A DOES see clan B's role row.

    That is ADR-050 § 1, not a defect. It is asserted here because an absence nobody
    pinned is an absence nobody notices: the day someone makes this half clan-keyed
    without first moving ``get_current_clan_id`` (``app/core/security.py:249-254``),
    ``get_login_profile`` (``auth_repository.py:120-137``) and ``list_clans``
    (``me_query_port.py:19-42``) off the request session, this test fails and points at
    the ADR that priced that move.

    The application layer is this table's only READ isolation, and
    ``app/infrastructure/persistence/clan_repository.py`` supplies it with an explicit
    ``clan_id`` filter on every list and count (``:84``, ``:96``, ``:100``, ``:106``).
    """
    clan_a, _clan_b, ucr_a, ucr_b = await _seed_two(engine)
    set_request_clan_id(clan_a)
    async with _rls(engine)() as s:
        visible = set(
            (
                await s.execute(
                    sa.text("SELECT id FROM user_clan_roles WHERE id IN (:a, :b)"),
                    {"a": ucr_a, "b": ucr_b},
                )
            )
            .scalars()
            .all()
        )
    assert visible == {ucr_a, ucr_b}


async def test_an_insert_naming_any_clan_is_admitted_with_no_clan_selected(
    engine: AsyncEngine,
) -> None:
    """``user_clan_roles_ins`` is ``WITH CHECK (true)``, and ``POST /auth/onboard`` is why.

    That route writes the caller's own membership on the request session with no clan
    selected, and on the ``create`` branch the clan does not exist until the request makes
    it. A clan-keyed ``WITH CHECK`` compares ``<real clan> = NULL`` and answers 500 —
    re-measured 2026-08-22, and the four cases in ``test_rls_login_two_clans.py`` are the
    end-to-end proof over the real routes. This one is the statement underneath them.
    """
    clan_a, _clan_b, _ucr_a, _ucr_b = await _seed_two(engine)
    user_id = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:i, :e, 'u')"),
            {"i": user_id, "e": f"{user_id.hex[:12]}@example.com"},
        )
    ucr_id = uuid.uuid4()
    set_request_clan_id(None)
    async with _rls(engine)() as s:
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(id, clan_id, user_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:id, :c, :u, 'admin', true, :u, now())"
            ),
            {"id": ucr_id, "c": clan_a, "u": user_id},
        )
        await s.commit()
    assert await _privileged_row(engine, ucr_id) == ("admin", True)


async def test_the_seam_really_was_active_during_those_statements(engine: AsyncEngine) -> None:
    """Guard for everything above: prove the fixture session is the NON-privileged request
    role. Without it, a fixture quietly handing out a privileged session would make every
    positive case pass and every denial fail for the wrong reason."""
    clan_a, _clan_b, _ucr_a, _ucr_b = await _seed_two(engine)
    set_request_clan_id(clan_a)
    async with _rls(engine)() as s:
        assert await s.scalar(sa.text("SELECT current_user")) == "familyroots_app"
        assert await s.scalar(sa.text("SELECT current_setting('app.clan_id', true)")) == str(clan_a)
