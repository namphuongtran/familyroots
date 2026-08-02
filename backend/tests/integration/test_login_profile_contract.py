"""Login must return a correct, deterministic profile (contract: rest-auth-api.md).

Three long-standing gaps, all pinned here:
- has_pending_membership was never computed at login (always false) — only
  GET /auth/me queried it, so login and /me disagreed for the same user.
- get_login_profile was LIMIT 1 with no ORDER BY and no approval preference:
  a user approved in clan A but pending in clan B could be told their clan is
  B with role null. Approved memberships must win, oldest first.
- preferred_locale was never echoed (always default "vi") even after
  PATCH /auth/me stored one.

The identity provider is the only stubbed seam (same approach as
test_auth_http_flow.py); the login profile projection runs against real
Postgres.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import get_current_user
from app.domain.auth.identity_provider import AuthenticatedIdentity, AuthTokens
from app.infrastructure.dependencies import get_identity_provider
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_PASSWORD = "correct-horse"


class _StubIdentity:
    """sign_in-only stub; the login profile projection is what's under test."""

    def __init__(self, user_id: str, preferred_locale: str | None = None) -> None:
        self._user_id = user_id
        self._preferred_locale = preferred_locale

    async def sign_in(self, *, email: str, password: str) -> AuthenticatedIdentity:
        return AuthenticatedIdentity(
            user_id=self._user_id,
            email=email,
            full_name="Đa Tộc",
            preferred_locale=self._preferred_locale,
            tokens=AuthTokens(access_token="at", refresh_token="rt", expires_in=3600),
        )


@pytest.fixture()
async def session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


@pytest.fixture()
async def seeded(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """User approved (admin) in clan A, pending in clan B.

    The pending row is inserted FIRST and with an older created_at, so an
    unordered LIMIT 1 would surface it — the approved membership must win
    regardless of physical/insertion order.
    """
    user_id = uuid.uuid4()
    email = f"{user_id.hex[:12]}@example.com"
    clan_a = uuid.uuid4()
    clan_b = uuid.uuid4()
    async with session_factory() as s:
        for cid, name in ((clan_a, "Clan A"), (clan_b, "Clan B")):
            await s.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :s)"),
                {"id": cid, "n": name, "s": f"c-{cid.hex[:8]}"},
            )
        await s.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'u')"),
            {"id": user_id, "e": email},
        )
        # Pending in B first (older row) …
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles (user_id, clan_id, role, is_approved, created_at) "
                "VALUES (:uid, :cid, 'viewer', false, now() - interval '1 day')"
            ),
            {"uid": user_id, "cid": clan_b},
        )
        # … approved admin in A second (newer row).
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at, created_at) "
                "VALUES (:uid, :cid, 'admin', true, :uid, now(), now())"
            ),
            {"uid": user_id, "cid": clan_a},
        )
        await s.commit()
    return {"user_id": user_id, "email": email, "clan_a": clan_a, "clan_b": clan_b}


def _app(session_factory: async_sessionmaker[AsyncSession], identity: _StubIdentity) -> Any:
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_identity_provider] = lambda: identity
    return app


async def test_login_prefers_approved_membership_and_reports_pending(
    session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, Any]
) -> None:
    app = _app(session_factory, _StubIdentity(str(seeded["user_id"])))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/v1/auth/login", json={"email": seeded["email"], "password": _PASSWORD}
        )
    assert resp.status_code == 200, resp.text
    user = resp.json()["data"]["user"]
    assert user["clan_id"] == str(seeded["clan_a"])  # approved wins over older pending
    assert user["role"] == "admin"
    assert user["is_approved"] is True
    assert user["has_pending_membership"] is True  # the pending clan-B row


async def test_login_echoes_preferred_locale(
    session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, Any]
) -> None:
    app = _app(session_factory, _StubIdentity(str(seeded["user_id"]), preferred_locale="en"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/v1/auth/login", json={"email": seeded["email"], "password": _PASSWORD}
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["user"]["preferred_locale"] == "en"


@pytest.fixture()
async def two_approved(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """A user approved in TWO clans, with distinct join dates.

    The row that must win (``first_joined``, ``created_at`` 10 days ago) is
    inserted SECOND, so physical/insertion order disagrees with the documented
    order. ``created_at`` is the column ``/me/clans`` exposes as ``joined_at``.
    """
    user_id = uuid.uuid4()
    email = f"{user_id.hex[:12]}@example.com"
    first_joined = uuid.uuid4()
    later_joined = uuid.uuid4()
    async with session_factory() as s:
        for cid, name in ((first_joined, "Older Clan"), (later_joined, "Newer Clan")):
            await s.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :s)"),
                {"id": cid, "n": name, "s": f"c-{cid.hex[:8]}"},
            )
        await s.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'u')"),
            {"id": user_id, "e": email},
        )
        for cid, age in ((later_joined, "1 hour"), (first_joined, "10 days")):
            await s.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(user_id, clan_id, role, is_approved, approved_by, approved_at, created_at) "
                    f"VALUES (:uid, :cid, 'editor', true, :uid, now(), now() - interval '{age}')"
                ),
                {"uid": user_id, "cid": cid},
            )
        await s.commit()
    return {
        "user_id": user_id,
        "email": email,
        "first_joined": first_joined,
        "later_joined": later_joined,
    }


async def _login_clan_id(
    session_factory: async_sessionmaker[AsyncSession], seed: dict[str, Any]
) -> str | None:
    app = _app(session_factory, _StubIdentity(str(seed["user_id"])))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/v1/auth/login", json={"email": seed["email"], "password": _PASSWORD}
        )
    assert resp.status_code == 200, resp.text
    clan_id: str | None = resp.json()["data"]["user"]["clan_id"]
    return clan_id


async def test_multi_clan_login_is_deterministic_oldest_membership_wins(
    session_factory: async_sessionmaker[AsyncSession], two_approved: dict[str, Any]
) -> None:
    """ADR-035: two approved memberships → the oldest ``joined_at`` is the
    landing clan, and repeated logins never disagree.

    Negative control: drop the ORDER BY in ``get_login_profile`` and this is a
    coin flip — the documented clan is no longer guaranteed.
    """
    observed = {await _login_clan_id(session_factory, two_approved) for _ in range(6)}
    assert observed == {str(two_approved["first_joined"])}, (
        f"login is nondeterministic across repeated calls: {observed}"
    )


async def test_multi_clan_login_tiebreaks_on_clan_id_when_joined_at_ties(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """ADR-035 final tiebreak: identical ``joined_at`` → lowest ``clan_id`` wins.

    Two memberships created in the same transaction share a timestamp (``now()``
    is transaction-stable in Postgres), which is exactly the case a
    ``created_at``-only ordering leaves undefined.
    """
    user_id = uuid.uuid4()
    email = f"{user_id.hex[:12]}@example.com"
    clans = sorted([uuid.uuid4(), uuid.uuid4()])
    async with session_factory() as s:
        for cid in clans:
            await s.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Tie', :s)"),
                {"id": cid, "s": f"c-{cid.hex[:8]}"},
            )
        await s.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'u')"),
            {"id": user_id, "e": email},
        )
        # Reverse order on purpose: the higher clan_id row is written first.
        for cid in reversed(clans):
            await s.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(user_id, clan_id, role, is_approved, approved_by, approved_at, created_at) "
                    "VALUES (:uid, :cid, 'editor', true, :uid, now(), now())"
                ),
                {"uid": user_id, "cid": cid},
            )
        await s.commit()

    seed = {"user_id": user_id, "email": email}
    observed = {await _login_clan_id(session_factory, seed) for _ in range(4)}
    assert observed == {str(clans[0])}, f"tiebreak is not the lowest clan_id: {observed}"


async def test_me_echoes_preferred_locale_from_metadata(
    session_factory: async_sessionmaker[AsyncSession], seeded: dict[str, Any]
) -> None:
    app = _app(session_factory, _StubIdentity(str(seeded["user_id"])))

    async def _user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        return {
            "sub": str(seeded["user_id"]),
            "email": seeded["email"],
            "user_metadata": {"full_name": "Đa Tộc", "preferred_locale": "en"},
        }

    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.get("/api/v1/auth/me", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["preferred_locale"] == "en"
