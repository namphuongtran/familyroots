"""A sign-up whose email a former account's profile row still holds (#297, ADR-078).

``user_profiles.id`` has no foreign key to ``auth.users``, so a row outlives its
Supabase account and keeps its email under ``uq_user_profiles_email``. Supabase then
hands that email to a new account with a new ``sub``. Measured on ``main`` at
``6d5a160`` on 2026-10-24, before this change: ``POST /auth/register`` with that
email answered 409 ``conflict`` while a fresh email answered 201, and the register
compensation deleted the new Supabase user again, so the person could never sign up.
The issue expected a 500; the global IntegrityError handler had made it a 409.

ADR-078 decides the outcome: the former row gives up its email
(``<id>@released.invalid``) and keeps everything else, and the new ``sub`` gets a
fresh profile with nothing carried over. Each test here sends the request or runs
the writer, then reads the response and the rows. None asserts that a release
function exists or is called.

The identity seam is the in-memory provider from
``test_invitee_registers_with_no_clan.py``, which mints RS256 tokens the real
``verify_supabase_token`` accepts. Rate-limit budget: the register test spends 3 of
the 20 counted requests on its own function-scoped app; the platform route is not
counted.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.security import ensure_user_profile
from app.infrastructure.persistence._profile import ensure_profile_row
from tests.integration import test_invitee_registers_with_no_clan as invitee
from tests.integration.test_invitee_registers_with_no_clan import _PW, StubIdentityProvider

pytestmark = pytest.mark.integration

# The invitee module's identity seam, bound here so pytest collects its fixtures.
rsa_keys = invitee.rsa_keys
jwks_cache = invitee.jwks_cache
stub_identity = invitee.stub_identity
client = invitee.client


def _sync_engine(dsn: str) -> sa.Engine:
    return sa.create_engine(dsn.replace("+asyncpg", ""))


def _seed_former_account(dsn: str, *, tag: str) -> tuple[uuid.UUID, str, uuid.UUID]:
    """A profile row whose Supabase account is gone: it holds an email and an
    approved admin role in a clan. Returns (former_id, email, clan_id)."""
    former_id, clan_id = uuid.uuid4(), uuid.uuid4()
    email = f"{tag}-{former_id.hex[:8]}@example.com"
    eng = _sync_engine(dsn)
    try:
        with eng.begin() as conn:
            conn.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:c, 'C', :sl)"),
                {"c": clan_id, "sl": f"c-{clan_id.hex[:8]}"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name) "
                    "VALUES (:u, :e, 'Former Account')"
                ),
                {"u": former_id, "e": email},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO user_clan_roles (user_id, clan_id, role, is_approved, "
                    "approved_by, approved_at) VALUES (:u, :c, 'admin', true, :u, now())"
                ),
                {"u": former_id, "c": clan_id},
            )
    finally:
        eng.dispose()
    return former_id, email, clan_id


def _rows(dsn: str, sql: str, **params: Any) -> list[Any]:
    eng = _sync_engine(dsn)
    try:
        with eng.connect() as conn:
            return list(conn.execute(sa.text(sql), params).all())
    finally:
        eng.dispose()


def _assert_former_row_released_and_intact(
    dsn: str, former_id: uuid.UUID, clan_id: uuid.UUID
) -> None:
    """The former row keeps its id, name and role; only its email changed."""
    [(email, display_name)] = _rows(
        dsn, "SELECT email, display_name FROM user_profiles WHERE id = :u", u=former_id
    )
    assert email == f"{former_id}@released.invalid"
    assert display_name == "Former Account"
    roles = _rows(
        dsn,
        "SELECT role, is_approved FROM user_clan_roles WHERE user_id = :u AND clan_id = :c",
        u=former_id,
        c=clan_id,
    )
    assert [tuple(r) for r in roles] == [("admin", True)]


def test_register_with_a_former_accounts_email_answers_like_any_sign_up(
    client: TestClient, migrated_db_url: str, stub_identity: StubIdentityProvider
) -> None:
    former_id, email, clan_id = _seed_former_account(migrated_db_url, tag="reg297")

    held = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PW, "full_name": "Nguoi Moi"},
    )
    fresh = client.post(
        "/api/v1/auth/register",
        json={"email": f"fresh-{email}", "password": _PW, "full_name": "Nguoi Khac"},
    )
    # ADR-021: the held email must not answer differently from a fresh one.
    assert (held.status_code, held.json()) == (fresh.status_code, fresh.json())
    assert held.status_code == 201, held.text
    # The compensation did not run: the new Supabase account still exists.
    assert email in stub_identity._users

    login = client.post("/api/v1/auth/login", json={"email": email, "password": _PW})
    assert login.status_code == 200, login.text
    user = login.json()["data"]["user"]
    new_id = uuid.UUID(user["id"])
    assert new_id != former_id
    assert (user["clan_id"], user["role"]) == (None, None)

    [(new_email, new_name)] = _rows(
        migrated_db_url,
        "SELECT email, display_name FROM user_profiles WHERE id = :u",
        u=new_id,
    )
    assert (new_email, new_name) == (email, "Nguoi Moi")
    assert (
        _rows(migrated_db_url, "SELECT 1 FROM user_clan_roles WHERE user_id = :u", u=new_id) == []
    )
    _assert_former_row_released_and_intact(migrated_db_url, former_id, clan_id)


def test_first_request_through_ensure_user_profile_provisions_the_new_account(
    client: TestClient, migrated_db_url: str, stub_identity: StubIdentityProvider
) -> None:
    """The lazy path: an account that exists at the provider but has no row yet, as
    after a recovery or a sign-up made outside register. ``get_super_admin`` sits on
    ``ensure_user_profile``, so a non-admin's answer is 403 ``super_admin_required``,
    the same answer a brand-new email gets."""
    former_id, email, clan_id = _seed_former_account(migrated_db_url, tag="lazy297")
    new_id = uuid.uuid4()

    def _get(user_id: uuid.UUID, user_email: str) -> Any:
        token = stub_identity._mint(str(user_id), user_email, "Nguoi Moi")
        return client.get("/api/v1/platform/clans", headers={"Authorization": f"Bearer {token}"})

    held = _get(new_id, email)
    fresh_id = uuid.uuid4()
    fresh = _get(fresh_id, f"fresh-{email}")
    assert (held.status_code, held.json()) == (fresh.status_code, fresh.json())
    assert held.status_code == 403, held.text
    assert held.json()["error"]["code"] == "super_admin_required"

    [(new_email,)] = _rows(
        migrated_db_url, "SELECT email FROM user_profiles WHERE id = :u", u=new_id
    )
    assert new_email == email
    _assert_former_row_released_and_intact(migrated_db_url, former_id, clan_id)


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


async def test_concurrent_first_requests_release_the_email_once(
    engine: AsyncEngine, migrated_db_url: str
) -> None:
    """Two first requests for the new ``sub`` race: the release and the insert both
    run twice. Neither may raise, and the email ends on exactly one row."""
    former_id, email, clan_id = _seed_former_account(migrated_db_url, tag="race297")
    new_id = uuid.uuid4()
    current_user = {"sub": str(new_id), "email": email, "user_metadata": {}}
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _call() -> None:
        async with maker() as db:
            await ensure_user_profile(current_user, db)

    await asyncio.gather(_call(), _call())

    holders = _rows(migrated_db_url, "SELECT id FROM user_profiles WHERE email = :e", e=email)
    assert [r.id for r in holders] == [new_id]
    _assert_former_row_released_and_intact(migrated_db_url, former_id, clan_id)


@pytest.fixture()
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as s:
        yield s
        await s.rollback()


async def test_an_empty_email_is_never_released(session: AsyncSession) -> None:
    """Supabase vouches for no owner of an empty email, and two live accounts may
    both lack one, so the second insert keeps failing rather than taking the
    first account's row. Nothing here commits."""
    holder = await session.scalar(sa.text("SELECT id FROM user_profiles WHERE email = ''"))
    if holder is None:
        holder = uuid.uuid4()
        await session.execute(
            sa.text("INSERT INTO user_profiles (id, email) VALUES (:u, '')"), {"u": holder}
        )

    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await ensure_profile_row(session, uuid.uuid4(), "", "Second")

    assert (
        await session.scalar(
            sa.text("SELECT email FROM user_profiles WHERE id = :u"), {"u": holder}
        )
        == ""
    )


async def test_a_sub_that_already_has_a_row_takes_no_email(session: AsyncSession) -> None:
    """The release fires only for the insert it unblocks. A ``sub`` whose row exists
    inserts nothing, so another row holding the email it now signs in with keeps it.
    Nothing here commits."""
    own_id, other_id = uuid.uuid4(), uuid.uuid4()
    email = f"own297-{own_id.hex[:8]}@example.com"
    await session.execute(
        sa.text("INSERT INTO user_profiles (id, email) VALUES (:own, :old), (:other, :e)"),
        {"own": own_id, "old": f"old-{email}", "other": other_id, "e": email},
    )

    await ensure_profile_row(session, own_id, email, "Own")

    rows = await session.execute(
        sa.text("SELECT id, email FROM user_profiles WHERE id IN (:own, :other)"),
        {"own": own_id, "other": other_id},
    )
    assert dict(rows.tuples().all()) == {own_id: f"old-{email}", other_id: email}
