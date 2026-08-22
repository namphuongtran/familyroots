"""``user_clan_roles`` cannot take a clan policy, and this file is the standing proof.

The name says "login two clans" because S-009 opened it on the read half. It now covers
both halves of the table's hazard, read and write, because keeping one table's evidence in
one file is worth more than a tidy file name.

Seed S-009 named this check because getting the read half wrong locks users out silently
rather than loudly. The login path runs on ``get_db`` — the RLS request session — and it
runs BEFORE any clan is chosen, so ``app.clan_id`` is empty and the migration-027 predicate
(``clan_id = nullif(current_setting('app.clan_id', true), '')::uuid``) evaluates to NULL.
Any clan-isolation policy placed on a table that the pre-selection read touches turns
"this user belongs to two clans" into "this user belongs to none", and the user is told
they have no approved membership. No error is logged. Nothing fails closed loudly.

The pre-selection READS are, re-measured 2026-08-22 by S-010:

* ``SqlAlchemyAuthQueryPort.get_login_profile`` — ``user_clan_roles`` joined to ``clans``
  (``app/infrastructure/persistence/auth_repository.py:120-137``);
* ``SqlAlchemyMeQueryPort.list_clans`` — ``user_clan_roles`` joined to ``clans``
  (``app/infrastructure/persistence/me_query_port.py:19-42``);
* ``get_current_clan_id`` itself — ``user_clan_roles``
  (``app/core/security.py:249-254``), which runs before it sets the GUC at
  ``app/core/security.py:290``.

The pre-selection WRITE, which S-009 and S-010 both missed and S-010 measured:

* ``SqlAlchemyAuthRepository.add_membership``
  (``app/infrastructure/persistence/auth_repository.py:69-88``) INSERTs the
  ``user_clan_roles`` row for ``POST /auth/register`` and ``POST /auth/onboard`` on that
  same clan-less request session — ``get_auth_command_handler`` is wired to ``get_db``
  (``app/infrastructure/dependencies.py:192-202``).

All four touch ``user_clan_roles``, which migrations 031 and 035 both deliberately leave
alone, and none of them reads ``clan_memberships``, ``clan_invitations`` or
``clan_settings``. These tests drive the real routes over the real ``RlsSession`` seam, so
the day a migration puts a clan policy on a pre-selection table, they fail.

Negative control, re-run 2026-08-22 by S-010 by putting ``user_clan_roles`` in migration
035's table list. It breaks in both directions, and the two failures look nothing alike:

* **silently** — ``test_login_resolves_a_multi_clan_user_under_the_rls_seam`` fails with
  ``assert None == '<clan uuid>'``: login still answers ``200``, reporting that the user
  belongs to nowhere. ``test_me_clans_lists_both_clans_under_the_rls_seam`` fails with
  ``assert set() == {...}``. Neither logs an error;
* **loudly** — the two onboard tests below fail with
  ``psycopg.errors.InsufficientPrivilege: new row violates row-level security policy for
  table "user_clan_roles"``, surfacing as a 500.

That the same policy produces a silent lockout on one route and a 500 on another is the
reason the decision needs an ADR rather than a patch.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import RlsSession, get_db
from app.core.rls import set_request_clan_id
from app.core.security import get_current_user
from app.domain.auth.identity_provider import AuthenticatedIdentity, AuthTokens
from app.infrastructure.dependencies import get_identity_provider
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_PASSWORD = "correct-horse"


class _StubIdentity:
    """sign_in-only stub — the identity provider is the one seam that cannot be real
    here. Everything under test (the membership projection) runs against Postgres."""

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    async def sign_in(self, *, email: str, password: str) -> AuthenticatedIdentity:
        return AuthenticatedIdentity(
            user_id=self._user_id,
            email=email,
            full_name="Đa Tộc",
            preferred_locale=None,
            tokens=AuthTokens(access_token="at", refresh_token="rt", expires_in=3600),
        )


@pytest.fixture(autouse=True)
def _reset_clan_context() -> Generator[None]:
    set_request_clan_id(None)
    yield
    set_request_clan_id(None)


@pytest.fixture()
async def rls_session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    """The REQUEST session class, not a plain one. ``RlsSession`` carries the
    ``after_begin`` seam that drops to ``familyroots_app`` and sets ``app.clan_id`` — a
    plain session would run privileged and prove nothing about RLS."""
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(
        engine, sync_session_class=RlsSession, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


@pytest.fixture()
async def privileged_session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


@pytest.fixture()
async def two_clan_user(
    privileged_session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, Any]:
    """One user, approved in TWO clans, and a ``clan_memberships`` row in each clan so the
    table migration 031 protects is populated for both."""
    user_id = uuid.uuid4()
    email = f"{user_id.hex[:12]}@example.com"
    clan_one, clan_two = uuid.uuid4(), uuid.uuid4()
    async with privileged_session_factory() as s:
        for cid, name in ((clan_one, "Clan One"), (clan_two, "Clan Two")):
            await s.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :s)"),
                {"id": cid, "n": name, "s": f"c-{cid.hex[:8]}"},
            )
        await s.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'u')"),
            {"id": user_id, "e": email},
        )
        # Approved in both. The older membership (clan_one) is written SECOND, so
        # insertion order disagrees with the ADR-035 landing-clan order on purpose.
        for cid, age in ((clan_two, "1 hour"), (clan_one, "10 days")):
            await s.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(user_id, clan_id, role, is_approved, approved_by, approved_at, created_at) "
                    f"VALUES (:uid, :cid, 'editor', true, :uid, now(), now() - interval '{age}')"
                ),
                {"uid": user_id, "cid": cid},
            )
            person_id = uuid.uuid4()
            await s.execute(
                sa.text(
                    "INSERT INTO persons (id, full_name, created_by_clan_id, created_by) "
                    "VALUES (:id, 'Thành viên', :c, :uid)"
                ),
                {"id": person_id, "c": cid, "uid": user_id},
            )
            await s.execute(
                sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
                {"p": person_id, "c": cid},
            )
        await s.commit()
    return {
        "user_id": user_id,
        "email": email,
        "clan_one": clan_one,  # older membership → the ADR-035 landing clan
        "clan_two": clan_two,
    }


def _app(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    identity: _StubIdentity | None = None,
    current_user: dict[str, Any] | None = None,
) -> Any:
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    if identity is not None:
        app.dependency_overrides[get_identity_provider] = lambda: identity
    if current_user is not None:

        async def _user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
            return current_user

        app.dependency_overrides[get_current_user] = _user
    return app


async def test_login_resolves_a_multi_clan_user_under_the_rls_seam(
    rls_session_factory: async_sessionmaker[AsyncSession], two_clan_user: dict[str, Any]
) -> None:
    """Login succeeds on the RLS request session with no clan selected yet, and lands the
    user on the older of the two memberships (ADR-035). Under a policy on a pre-selection
    table the response stays ``200`` and ``clan_id`` becomes ``None`` — a lockout that
    looks like a successful login."""
    app = _app(rls_session_factory, identity=_StubIdentity(str(two_clan_user["user_id"])))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/v1/auth/login",
            json={"email": two_clan_user["email"], "password": _PASSWORD},
        )
    assert resp.status_code == 200, resp.text
    user = resp.json()["data"]["user"]
    assert user["clan_id"] == str(two_clan_user["clan_one"]), user
    assert user["is_approved"] is True


async def test_me_clans_lists_both_clans_under_the_rls_seam(
    rls_session_factory: async_sessionmaker[AsyncSession], two_clan_user: dict[str, Any]
) -> None:
    """``GET /me/clans`` is the clan switcher. It carries no ``X-Current-Clan-Id`` by
    design, so it runs with an empty GUC. BOTH memberships must come back — the assertion
    the seed asks for, and the one that catches a lockout that login alone would not."""
    app = _app(
        rls_session_factory,
        current_user={
            "sub": str(two_clan_user["user_id"]),
            "email": two_clan_user["email"],
            "user_metadata": {"full_name": "Đa Tộc"},
        },
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.get("/api/v1/me/clans", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200, resp.text
    returned = {row["clan_id"] for row in resp.json()["data"]}
    assert returned == {
        str(two_clan_user["clan_one"]),
        str(two_clan_user["clan_two"]),
    }, returned


async def _lone_user_profile(
    privileged_session_factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, str]:
    """A user with a profile and NO membership anywhere — the state onboarding starts from."""
    uid = uuid.uuid4()
    email = f"{uid.hex[:12]}@example.com"
    async with privileged_session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:i, :e, 'u')"),
            {"i": uid, "e": email},
        )
        await s.commit()
    return uid, email


async def test_onboard_create_writes_a_user_clan_roles_row_with_no_clan_selected(
    rls_session_factory: async_sessionmaker[AsyncSession],
    privileged_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The WRITE half of the hazard, and it fails loudly rather than silently.

    ``POST /auth/onboard`` with ``clan_action=create`` makes the clan and then INSERTs the
    caller's admin membership through ``add_membership``
    (``auth_repository.py:69-88``) on the RLS request session. No clan GUC exists yet — the
    route takes ``get_current_user`` and not ``get_current_clan_id``, and it could not take
    the latter, because the clan does not exist until this request creates it.

    Under a clan-keyed ``WITH CHECK`` that INSERT compares ``<the new clan> = NULL`` and
    Postgres raises ``InsufficientPrivilege``, which reaches the client as a 500.
    """
    uid, email = await _lone_user_profile(privileged_session_factory)
    app = _app(
        rls_session_factory,
        current_user={"sub": str(uid), "email": email, "user_metadata": {"full_name": "Tân"}},
    )
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
    body = resp.json()["data"]
    assert body["clan_id"], body
    assert body["is_approved"] is True, body

    async with privileged_session_factory() as s:  # privileged: the row is really there
        n = await s.scalar(
            sa.text("SELECT count(*) FROM user_clan_roles WHERE user_id = :u"), {"u": uid}
        )
    assert n == 1


async def test_onboard_join_writes_a_pending_user_clan_roles_row_with_no_clan_selected(
    rls_session_factory: async_sessionmaker[AsyncSession],
    privileged_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The same write on the join branch, which reaches an EXISTING clan.

    ``clan_action=join`` resolves the clan through ``get_clan_by_id``
    (``auth_repository.py:51-52``) and then stages a pending viewer membership. A reader
    might expect the join branch to be safe because a real clan id is in hand; it is not.
    The id is in the request body, never in ``app.clan_id``, so the predicate is still NULL.
    """
    clan_id = uuid.uuid4()
    async with privileged_session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:i, 'Họ Trần', :s)"),
            {"i": clan_id, "s": f"j{clan_id.hex[:10]}"},
        )
        await s.commit()
    uid, email = await _lone_user_profile(privileged_session_factory)

    app = _app(
        rls_session_factory,
        current_user={"sub": str(uid), "email": email, "user_metadata": {"full_name": "Tân"}},
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/v1/auth/onboard",
            headers={"Authorization": "Bearer x"},
            json={"clan_action": "join", "clan_id": str(clan_id)},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["clan_id"] == str(clan_id), body
    assert body["is_approved"] is False, body

    async with privileged_session_factory() as s:
        approved = await s.scalar(
            sa.text("SELECT is_approved FROM user_clan_roles WHERE user_id = :u"), {"u": uid}
        )
    assert approved is False


async def test_the_seam_really_was_active_during_those_requests(
    rls_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Guard for the two tests above: prove the fixture session is the NON-privileged
    request role with an empty ``app.clan_id``. Without this, a fixture that quietly
    handed out a privileged session would make both of them pass while proving nothing."""
    async with rls_session_factory() as s:
        assert await s.scalar(sa.text("SELECT current_user")) == "familyroots_app"
        assert await s.scalar(sa.text("SELECT current_setting('app.clan_id', true)")) == ""
