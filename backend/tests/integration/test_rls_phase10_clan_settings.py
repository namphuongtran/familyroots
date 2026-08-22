"""RLS layer-2 Phase 10 (S-010, ADR-008): clan_settings is clan-isolated at the DB.

Migration 035 gives ``clan_settings`` the migration-027 template, both halves clan-keyed.
The row is a clan's own configuration — its approval workflow, its privacy level, its
default language — so a cross-clan read here is a read of how another family has chosen to
run itself.

**This table is EMPTY and UNREAD in the running application on 2026-08-22**, which changes
what these tests have to do. Measured by ``grep -rn 'clan_settings\\|ClanSettings'
backend/app``: the only reference outside the ORM model is the ``Clan.settings``
relationship (``app/models/clan.py:35``); nothing reads ``clan.settings``, nothing
constructs a ``ClanSettings``, and ``001_initial.py`` installs no trigger that would create
one (its only triggers are ``trg_<table>_updated_at``, ``001_initial.py:930-937``). So every
denial assertion below ends with a **privileged** read proving the rows were really there —
S-012's rule, and it bites harder here than anywhere else, because on this table "zero rows
returned" is also the honest answer for the whole production database.

What these prove, all through the runtime seam (``RlsSession`` + the ``app.clan_id``
ContextVar) and asserted with naked SQL at the database layer, so no application-layer
``WHERE clan_id = …`` can stand in for the policy:

* isolation in BOTH directions — A cannot see B's settings, and B cannot see A's;
* an unset GUC yields zero rows (fail closed), with the rows proven present;
* a write naming the wrong clan is REJECTED with an error, on INSERT and on an UPDATE that
  tries to move a row across clans;
* an UPDATE and a DELETE aimed at the other clan's row change nothing, verified privileged;
* ``Clan.settings`` (``lazy="selectin"``) still resolves for the active clan, and comes back
  ``None`` rather than raising when no clan is selected;
* and the two live clan-less request paths that fire that selectin — ``POST /auth/onboard``
  with ``clan_action=create`` and with ``clan_action=join`` — still answer ``201``. Those two
  are the reason this migration is safe and ``user_clan_roles`` is not; see the migration
  docstring, and ``test_rls_login_two_clans.py`` for the table that had to be left out.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import RlsSession, get_db
from app.core.rls import set_request_clan_id
from app.core.security import get_current_user
from app.main import create_app
from app.models.clan import Clan

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


async def _settings(conn: AsyncConnection, clan_id: uuid.UUID, language: str) -> uuid.UUID:
    sid = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO clan_settings (id, clan_id, default_language) VALUES (:id, :c, :lang)"
        ),
        {"id": sid, "c": clan_id, "lang": language},
    )
    return sid


async def _seed_two(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Two clans, each with a settings row. Seeding runs privileged (RLS-bypassing).

    Returns ``(clan_a, clan_b, settings_a, settings_b)``.
    """
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan_a)
        await _clan(conn, clan_b)
        s_a = await _settings(conn, clan_a, "vi")
        s_b = await _settings(conn, clan_b, "en")
    return clan_a, clan_b, s_a, s_b


def _rls(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine, sync_session_class=RlsSession, expire_on_commit=False, class_=AsyncSession
    )


async def _privileged_ids(engine: AsyncEngine, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Read the named settings rows on a privileged connection.

    Every denial below calls this. Without it, a migration that dropped the rows, a
    fixture that never wrote them, and a policy that works are indistinguishable — and on
    THIS table the empty answer is the one production would give.
    """
    async with engine.connect() as conn:
        rows = await conn.execute(
            sa.text("SELECT id FROM clan_settings WHERE id = ANY(:ids)"), {"ids": ids}
        )
        return set(rows.scalars())


async def test_the_seam_is_the_non_privileged_role(engine: AsyncEngine) -> None:
    """Guard for every test below: the fixture session really is ``familyroots_app``.

    A fixture quietly handing out a privileged session would make the positive assertions
    pass while proving nothing about any policy.
    """
    clan_a, _b, _sa, _sb = await _seed_two(engine)
    set_request_clan_id(clan_a)
    async with _rls(engine)() as s:
        assert await s.scalar(sa.text("SELECT current_user")) == "familyroots_app"
        assert await s.scalar(sa.text("SELECT current_setting('app.clan_id', true)")) == str(clan_a)


async def test_reads_are_scoped_to_the_active_clan_in_both_directions(
    engine: AsyncEngine,
) -> None:
    """Two-sided: under clan A the database returns A's settings row and not B's, and under
    clan B the reverse. One direction alone also passes on a policy that hides everything.
    """
    clan_a, clan_b, s_a, s_b = await _seed_two(engine)
    rls = _rls(engine)

    set_request_clan_id(clan_a)
    async with rls() as s:
        seen_by_a = set((await s.execute(sa.text("SELECT id FROM clan_settings"))).scalars())
    assert s_a in seen_by_a, seen_by_a
    assert s_b not in seen_by_a, seen_by_a

    set_request_clan_id(clan_b)
    async with rls() as s:
        seen_by_b = set((await s.execute(sa.text("SELECT id FROM clan_settings"))).scalars())
    assert s_b in seen_by_b, seen_by_b
    assert s_a not in seen_by_b, seen_by_b

    assert await _privileged_ids(engine, [s_a, s_b]) == {s_a, s_b}


async def test_targeted_read_of_the_other_clans_settings_returns_nothing(
    engine: AsyncEngine,
) -> None:
    """Asking for the other clan's settings BY ID — the shape a missed repository filter
    produces — returns no row, in both directions, while the caller's own row is returned.
    """
    clan_a, clan_b, s_a, s_b = await _seed_two(engine)
    rls = _rls(engine)
    by_id = sa.text("SELECT count(*) FROM clan_settings WHERE id = :id")

    set_request_clan_id(clan_a)
    async with rls() as s:
        assert await s.scalar(by_id, {"id": s_b}) == 0
        assert await s.scalar(by_id, {"id": s_a}) == 1

    set_request_clan_id(clan_b)
    async with rls() as s:
        assert await s.scalar(by_id, {"id": s_a}) == 0
        assert await s.scalar(by_id, {"id": s_b}) == 1

    assert await _privileged_ids(engine, [s_a, s_b]) == {s_a, s_b}


async def test_the_other_clans_configuration_values_do_not_leak(engine: AsyncEngine) -> None:
    """The point of the table is the VALUES, not the row id. Under clan A a scan of
    ``default_language`` returns only A's, and B's differing value is nowhere in it."""
    clan_a, clan_b, s_a, s_b = await _seed_two(engine)  # A is 'vi', B is 'en'
    rls = _rls(engine)

    set_request_clan_id(clan_a)
    async with rls() as s:
        langs_a = set(
            (await s.execute(sa.text("SELECT default_language FROM clan_settings"))).scalars()
        )
    assert langs_a == {"vi"}, langs_a

    set_request_clan_id(clan_b)
    async with rls() as s:
        langs_b = set(
            (await s.execute(sa.text("SELECT default_language FROM clan_settings"))).scalars()
        )
    assert langs_b == {"en"}, langs_b

    assert await _privileged_ids(engine, [s_a, s_b]) == {s_a, s_b}


async def test_default_deny_when_no_clan(engine: AsyncEngine) -> None:
    """An unset GUC yields NULL, so the predicate is NULL and no row is visible.

    The privileged read at the end is not decoration: this table is empty in the running
    application, so ``count(*) == 0`` proves nothing on its own.
    """
    _a, _b, s_a, s_b = await _seed_two(engine)
    set_request_clan_id(None)
    async with _rls(engine)() as s:
        assert await s.scalar(sa.text("SELECT count(*) FROM clan_settings")) == 0
    assert await _privileged_ids(engine, [s_a, s_b]) == {s_a, s_b}


async def test_with_check_rejects_a_cross_clan_insert(engine: AsyncEngine) -> None:
    """Under GUC = clan A, inserting a settings row labelled clan B RAISES. The write is
    rejected, not silently dropped — a silently dropped write would let an admin believe
    they had reconfigured a clan."""
    clan_a, clan_b, _sa, _sb = await _seed_two(engine)
    set_request_clan_id(clan_a)
    async with _rls(engine)() as s:
        with pytest.raises(sa.exc.DBAPIError) as ei:
            await s.execute(
                sa.text(
                    "INSERT INTO clan_settings (id, clan_id, default_language) "
                    "VALUES (:id, :c, 'fr')"
                ),
                {"id": uuid.uuid4(), "c": clan_b},
            )
            await s.flush()
        assert "row-level security" in str(ei.value).lower()


async def test_with_check_rejects_moving_a_settings_row_to_another_clan(
    engine: AsyncEngine,
) -> None:
    """Under GUC = clan A, moving A's own settings row into clan B RAISES. ``USING`` admits
    the row for the update; ``WITH CHECK`` refuses the new one."""
    clan_a, clan_b, s_a, _sb = await _seed_two(engine)
    set_request_clan_id(clan_a)
    async with _rls(engine)() as s:
        with pytest.raises(sa.exc.DBAPIError) as ei:
            await s.execute(
                sa.text("UPDATE clan_settings SET clan_id = :c WHERE id = :id"),
                {"c": clan_b, "id": s_a},
            )
            await s.flush()
        assert "row-level security" in str(ei.value).lower()


async def test_update_of_the_other_clans_settings_touches_no_row(engine: AsyncEngine) -> None:
    """Under clan A, flipping B's tree to public matches nothing, and B's row is unchanged
    — checked privileged, because the policy that hid the row also hides the damage."""
    clan_a, _clan_b, _sa, s_b = await _seed_two(engine)
    set_request_clan_id(clan_a)
    async with _rls(engine)() as s:
        updated = (
            (
                await s.execute(
                    sa.text(
                        "UPDATE clan_settings SET allow_public_tree = true "
                        "WHERE id = :id RETURNING id"
                    ),
                    {"id": s_b},
                )
            )
            .scalars()
            .all()
        )
        assert list(updated) == []
        await s.commit()

    async with engine.connect() as conn:  # privileged: sees every clan
        allow_public = await conn.scalar(
            sa.text("SELECT allow_public_tree FROM clan_settings WHERE id = :id"), {"id": s_b}
        )
    assert allow_public is False


async def test_delete_of_the_other_clans_settings_touches_no_row(engine: AsyncEngine) -> None:
    """Under clan A a DELETE cannot reach B's settings row — verified privileged, because a
    policy that hides the row also hides its absence."""
    clan_a, _clan_b, _sa, s_b = await _seed_two(engine)
    set_request_clan_id(clan_a)
    async with _rls(engine)() as s:
        await s.execute(sa.text("DELETE FROM clan_settings WHERE id = :id"), {"id": s_b})
        await s.commit()
    assert await _privileged_ids(engine, [s_b]) == {s_b}


async def test_clan_settings_selectin_resolves_for_the_active_clan_and_is_none_without_one(
    engine: AsyncEngine,
) -> None:
    """``Clan.settings`` is ``lazy="selectin"`` (``app/models/clan.py:35``), so loading a
    ``Clan`` ORM entity emits a second SELECT against this table. That is the ONLY live
    reader in the application today, and it runs on the request session.

    With the right clan selected it must still resolve. With no clan selected it must come
    back ``None`` rather than raising — a raise would turn ``POST /auth/onboard`` into a 500,
    which is what the two HTTP tests below guard end to end.
    """
    clan_a, _clan_b, s_a, _sb = await _seed_two(engine)
    rls = _rls(engine)

    set_request_clan_id(clan_a)
    async with rls() as s:
        clan = (await s.execute(sa.select(Clan).where(Clan.id == clan_a))).scalar_one()
        assert clan.settings is not None
        assert clan.settings.id == s_a

    set_request_clan_id(None)
    async with rls() as s:
        clan = (await s.execute(sa.select(Clan).where(Clan.id == clan_a))).scalar_one()
        assert clan.settings is None
    assert await _privileged_ids(engine, [s_a]) == {s_a}


def _onboard_app(factory: async_sessionmaker[AsyncSession], user: dict[str, Any]) -> Any:
    app = create_app()

    async def _db() -> AsyncGenerator[AsyncSession]:
        async with factory() as session:
            yield session

    async def _user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    return app


async def _user_profile(engine: AsyncEngine) -> tuple[uuid.UUID, str]:
    uid = uuid.uuid4()
    email = f"{uid.hex[:12]}@example.com"
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:i, :e, 'u')"),
            {"i": uid, "e": email},
        )
    return uid, email


async def test_onboard_create_still_succeeds_with_the_policy_live(engine: AsyncEngine) -> None:
    """``POST /auth/onboard`` (``clan_action=create``) runs on ``get_db`` — the RLS request
    session — with NO clan GUC, and its slug pre-check calls ``get_clan_by_slug``
    (``auth_repository.py:47-49``), a ``select(Clan)`` whose selectin reaches this table.

    A 201 here is the evidence that adding ``clan_settings`` to layer 2 did not break the
    clan-less auth path. It is also the exact assertion that FAILS if someone adds
    ``user_clan_roles`` to a policy migration: that INSERT raises
    ``InsufficientPrivilege`` on this same request.
    """
    uid, email = await _user_profile(engine)
    app = _onboard_app(_rls(engine), {"sub": str(uid), "email": email, "user_metadata": {}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/v1/auth/onboard",
            headers={"Authorization": "Bearer x"},
            json={
                "clan_action": "create",
                "clan_name": "Họ Nguyễn",
                "clan_slug": f"s{uid.hex[:8]}",
            },
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["clan_id"], resp.text


async def test_onboard_join_still_succeeds_with_the_policy_live(engine: AsyncEngine) -> None:
    """``clan_action=join`` resolves the target clan through ``get_clan_by_id``
    (``auth_repository.py:51-52``), an ORM ``Session.get`` — which also fires the selectin
    against a clan_settings row that DOES exist here, on a session with no clan GUC.

    The row is invisible to that read and the request must still succeed, because nothing
    consumes ``clan.settings``. If that ever changes, this is the test that catches it.
    """
    clan_id = uuid.uuid4()
    async with engine.begin() as conn:
        await _clan(conn, clan_id)
        await _settings(conn, clan_id, "vi")
    uid, email = await _user_profile(engine)

    app = _onboard_app(_rls(engine), {"sub": str(uid), "email": email, "user_metadata": {}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/v1/auth/onboard",
            headers={"Authorization": "Bearer x"},
            json={"clan_action": "join", "clan_id": str(clan_id)},
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["clan_id"] == str(clan_id), resp.text
    assert resp.json()["data"]["is_approved"] is False, resp.text
