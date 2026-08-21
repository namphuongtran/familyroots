"""A multi-clan user can still log in and see BOTH clans once RLS reaches more tables.

Seed S-009 names this check because getting it wrong locks users out silently rather than
loudly. The login path runs on ``get_db`` — the RLS request session — and it runs BEFORE
any clan is chosen, so ``app.clan_id`` is empty and the migration-027 predicate
(``clan_id = nullif(current_setting('app.clan_id', true), '')::uuid``) evaluates to NULL.
Any clan-isolation policy placed on a table that the pre-selection read touches turns
"this user belongs to two clans" into "this user belongs to none", and the user is told
they have no approved membership. No error is logged. Nothing fails closed loudly.

The pre-selection reads are, at 2026-08-22:

* ``SqlAlchemyAuthQueryPort.get_login_profile`` — ``user_clan_roles`` joined to ``clans``
  (``app/infrastructure/persistence/auth_repository.py:118-135``);
* ``SqlAlchemyMeQueryPort.list_clans`` — ``user_clan_roles`` joined to ``clans``
  (``app/infrastructure/persistence/me_query_port.py:19-42``);
* ``get_current_clan_id`` itself — ``user_clan_roles``
  (``app/core/security.py:246-253``), which runs before it sets the GUC at
  ``app/core/security.py:290``.

All three read ``user_clan_roles``, which migration 031 deliberately does not touch, and
none of them reads ``clan_memberships`` or ``clan_invitations``. This test is the standing
proof of that: it drives the real routes over the real ``RlsSession`` seam, so the day a
migration puts a clan policy on a pre-selection table, this fails.

Negative control (run 2026-08-22): adding ``user_clan_roles`` to migration 031's table
list makes both tests below fail. Login still answers ``200``, but with
``clan_id: None`` — the user is told they belong to nowhere — and ``GET /me/clans``
returns ``[]``. Neither logs an error. That silence is the whole reason this file exists.
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


async def test_the_seam_really_was_active_during_those_requests(
    rls_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Guard for the two tests above: prove the fixture session is the NON-privileged
    request role with an empty ``app.clan_id``. Without this, a fixture that quietly
    handed out a privileged session would make both of them pass while proving nothing."""
    async with rls_session_factory() as s:
        assert await s.scalar(sa.text("SELECT current_user")) == "familyroots_app"
        assert await s.scalar(sa.text("SELECT current_setting('app.clan_id', true)")) == ""
