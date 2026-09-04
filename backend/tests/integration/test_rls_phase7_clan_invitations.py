"""RLS layer-2 Phase 7 (ADR-048): clan_invitations is clan-isolated at the DB.

Migration 032 enables the migration-027 clan-isolation policy on ``clan_invitations``. The
row says "this clan has offered this email address a role", which is membership intent plus
an email address plus a bearer token. A cross-clan read here hands another clan a working
invitation token, so the write side matters as much as the read side.

These prove enforcement through the runtime seam (``RlsSession`` + the ``app.clan_id``
ContextVar), and they assert at the database layer with naked SQL rather than through the
API, so an application-layer ``WHERE clan_id = …`` cannot stand in for the policy:

* isolation in BOTH directions — A cannot see B's invitation, and B cannot see A's;
* the TOKEN lookup, which is the one query in the aggregate with no ``clan_id`` predicate,
  is scoped by the policy alone — this is the exact shape that made ADR-048 necessary;
* a write for the wrong clan is REJECTED (an error), never silently ignored, on INSERT and
  on an UPDATE that tries to move a row into another clan;
* a revoke aimed at the other clan's invitation touches no row, checked privileged, because
  a policy that hides the row also hides the damage;
* the same email invited by two clans is two rows, and each clan sees only its own — the
  case a one-sided test misses;
* no clan set → zero rows (fail closed), which is why the accept path had to move off this
  session in the first place.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta

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


async def _invitation(
    conn: AsyncConnection, clan_id: uuid.UUID, *, email: str | None = None
) -> tuple[uuid.UUID, str]:
    inv_id = uuid.uuid4()
    token = f"tok-{uuid.uuid4().hex}"
    await conn.execute(
        sa.text(
            "INSERT INTO clan_invitations (id, clan_id, email, role, invited_by, token, "
            "expires_at, status) VALUES (:id, :c, :e, 'editor', :ib, :t, :exp, 'pending')"
        ),
        {
            "id": inv_id,
            "c": clan_id,
            "e": email or f"{inv_id.hex[:12]}@example.com",
            "ib": uuid.uuid4(),
            "t": token,
            "exp": datetime.now(UTC) + timedelta(days=7),
        },
    )
    return inv_id, token


async def _seed_two(
    engine: AsyncEngine,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, str, str]:
    """Two clans, one pending invitation each.

    Returns ``(clan_a, clan_b, inv_a, inv_b, token_a, token_b)``. Seeding runs on the
    privileged connection, which bypasses RLS.
    """
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan_a)
        await _clan(conn, clan_b)
        inv_a, token_a = await _invitation(conn, clan_a)
        inv_b, token_b = await _invitation(conn, clan_b)
    return clan_a, clan_b, inv_a, inv_b, token_a, token_b


def _rls(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine, sync_session_class=RlsSession, expire_on_commit=False, class_=AsyncSession
    )


async def test_reads_are_scoped_to_the_active_clan_in_both_directions(engine: AsyncEngine) -> None:
    """Two-sided: under clan A the DB returns A's invitation and not B's, and under clan B the
    reverse. One direction alone would also pass on a policy that hides everything."""
    clan_a, clan_b, inv_a, inv_b, _ta, _tb = await _seed_two(engine)
    rls = _rls(engine)

    set_request_clan_id(clan_a)
    async with rls() as s:
        seen_by_a = set((await s.execute(sa.text("SELECT id FROM clan_invitations"))).scalars())
    assert inv_a in seen_by_a, seen_by_a
    assert inv_b not in seen_by_a, seen_by_a

    set_request_clan_id(clan_b)
    async with rls() as s:
        seen_by_b = set((await s.execute(sa.text("SELECT id FROM clan_invitations"))).scalars())
    assert inv_b in seen_by_b, seen_by_b
    assert inv_a not in seen_by_b, seen_by_b


async def test_lookup_by_token_is_scoped_by_the_policy_alone(engine: AsyncEngine) -> None:
    """``get_by_token`` (``invitation_repository.py:53-58``) has NO ``clan_id`` predicate,
    because the token is the authorization. It is therefore the one query on this table with
    no application-layer filter behind it, and the policy is the only thing scoping it.

    Two-sided: under clan A the other clan's token resolves to nothing, and under clan B the
    reverse. This is the exact query whose behaviour forced ADR-048.
    """
    clan_a, clan_b, _ia, _ib, token_a, token_b = await _seed_two(engine)
    rls = _rls(engine)
    by_token = sa.text("SELECT count(*) FROM clan_invitations WHERE token = :t")

    set_request_clan_id(clan_a)
    async with rls() as s:
        assert await s.scalar(by_token, {"t": token_a}) == 1
        assert await s.scalar(by_token, {"t": token_b}) == 0

    set_request_clan_id(clan_b)
    async with rls() as s:
        assert await s.scalar(by_token, {"t": token_b}) == 1
        assert await s.scalar(by_token, {"t": token_a}) == 0


async def test_same_email_invited_by_two_clans_stays_split(engine: AsyncEngine) -> None:
    """One person invited by A and by B. Each clan sees its OWN offer and not the other's.

    This is the case a one-sided test misses entirely: the email is legitimately known to
    both clans, so only the policy can hide the fact that the other clan also invited them.
    """
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    email = f"{uuid.uuid4().hex[:12]}@example.com"
    async with engine.begin() as conn:
        await _clan(conn, clan_a)
        await _clan(conn, clan_b)
        inv_a, _ta = await _invitation(conn, clan_a, email=email)
        inv_b, _tb = await _invitation(conn, clan_b, email=email)

    rls = _rls(engine)
    by_email = sa.text("SELECT id FROM clan_invitations WHERE email = :e")

    set_request_clan_id(clan_a)
    async with rls() as s:
        assert set((await s.execute(by_email, {"e": email})).scalars()) == {inv_a}

    set_request_clan_id(clan_b)
    async with rls() as s:
        assert set((await s.execute(by_email, {"e": email})).scalars()) == {inv_b}


async def test_default_deny_when_no_clan(engine: AsyncEngine) -> None:
    """An unset GUC yields NULL, so the predicate is NULL and no row is visible. This is the
    behaviour that made the accept path unworkable on the request session (ADR-048)."""
    await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(None)
    async with rls() as s:
        assert await s.scalar(sa.text("SELECT count(*) FROM clan_invitations")) == 0


async def test_with_check_rejects_a_cross_clan_insert(engine: AsyncEngine) -> None:
    """Under GUC = clan A, inviting somebody on clan B's behalf RAISES. The write is rejected,
    not silently dropped — an ignored write would leave the admin believing an invitation had
    been sent, and would leave no row for anyone to revoke."""
    clan_a, clan_b, _ia, _ib, _ta, _tb = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        with pytest.raises(sa.exc.DBAPIError) as ei:
            await s.execute(
                sa.text(
                    "INSERT INTO clan_invitations (id, clan_id, email, role, invited_by, "
                    "token, expires_at, status) VALUES (:id, :c, :e, 'editor', :ib, :t, "
                    ":exp, 'pending')"
                ),
                {
                    "id": uuid.uuid4(),
                    "c": clan_b,
                    "e": "victim@example.com",
                    "ib": uuid.uuid4(),
                    "t": f"tok-{uuid.uuid4().hex}",
                    "exp": datetime.now(UTC) + timedelta(days=7),
                },
            )
            await s.flush()
        assert "row-level security" in str(ei.value).lower()


async def test_with_check_rejects_reassigning_an_invitation_to_another_clan(
    engine: AsyncEngine,
) -> None:
    """Under GUC = clan A, moving A's own invitation into clan B RAISES. USING admits the row
    for the update, WITH CHECK refuses the new one."""
    clan_a, clan_b, inv_a, _ib, _ta, _tb = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        with pytest.raises(sa.exc.DBAPIError) as ei:
            await s.execute(
                sa.text("UPDATE clan_invitations SET clan_id = :c WHERE id = :id"),
                {"c": clan_b, "id": inv_a},
            )
            await s.flush()
        assert "row-level security" in str(ei.value).lower()


async def test_revoking_the_other_clans_invitation_touches_no_row(engine: AsyncEngine) -> None:
    """Revoke is ``transition_status`` (``invitation_repository.py:107-127``), an UPDATE that
    matches by ``id`` and ``status`` with no ``clan_id``. Under clan A it cannot reach B's
    row — checked with a privileged read, because the policy that hid the row would also hide
    the damage."""
    clan_a, _clan_b, _ia, inv_b, _ta, _tb = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        updated = (
            (
                await s.execute(
                    sa.text(
                        "UPDATE clan_invitations SET status = 'revoked' "
                        "WHERE id = :id AND status = 'pending' RETURNING id"
                    ),
                    {"id": inv_b},
                )
            )
            .scalars()
            .all()
        )
        assert list(updated) == []
        await s.commit()

    async with engine.connect() as conn:  # privileged: sees every clan
        status = await conn.scalar(
            sa.text("SELECT status FROM clan_invitations WHERE id = :id"), {"id": inv_b}
        )
    assert status == "pending"


async def test_delete_of_the_other_clans_invitation_touches_no_row(engine: AsyncEngine) -> None:
    """The blunt version of the same thing. Under clan A a DELETE cannot reach B's row."""
    clan_a, _clan_b, _ia, inv_b, _ta, _tb = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(clan_a)
    async with rls() as s:
        await s.execute(sa.text("DELETE FROM clan_invitations WHERE id = :id"), {"id": inv_b})
        await s.commit()

    async with engine.connect() as conn:
        still_there = await conn.scalar(
            sa.text("SELECT count(*) FROM clan_invitations WHERE id = :id"), {"id": inv_b}
        )
    assert still_there == 1


async def test_insert_for_the_active_clan_still_works(engine: AsyncEngine) -> None:
    """The create path, which must keep working under the policy: an INSERT whose ``clan_id``
    IS the active clan is admitted, and the row is readable back in the same session."""
    clan_a, _clan_b, _ia, _ib, _ta, _tb = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(clan_a)

    new_id, token = uuid.uuid4(), f"tok-{uuid.uuid4().hex}"
    async with rls() as s:
        await s.execute(
            sa.text(
                "INSERT INTO clan_invitations (id, clan_id, email, role, invited_by, token, "
                "expires_at, status) VALUES (:id, :c, :e, 'editor', :ib, :t, :exp, 'pending')"
            ),
            {
                "id": new_id,
                "c": clan_a,
                "e": "newcomer@example.com",
                "ib": uuid.uuid4(),
                "t": token,
                "exp": datetime.now(UTC) + timedelta(days=7),
            },
        )
        await s.commit()

    set_request_clan_id(clan_a)
    async with rls() as s:
        assert (
            await s.scalar(
                sa.text("SELECT count(*) FROM clan_invitations WHERE id = :id"), {"id": new_id}
            )
            == 1
        )
