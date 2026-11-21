"""``DELETE /api/v1/auth/me`` — a signed-in user deletes their own account (ADR-079, #333).

Every case reads outcomes, per ``.claude/rules/testing.md``: the rows that remain in
Postgres after the request, read on a privileged connection, and the calls the identity
fake received. None of them asks whether a handler method ran.

**Wiring is production's.** ``get_db`` is a real ``RlsSession`` (the request role) and
``get_system_db`` is the privileged maker, the split ``create_app`` uses. The route
depends on ``get_system_db`` for its writes (``get_account_deletion_handler``), and
``get_current_user`` is the only dependency replaced, so JWT verification is the one
thing not exercised.

Negative controls run 2026-11-21, each seen to fail and then reverted:

- ``get_account_deletion_handler`` re-pointed at ``get_db``: under the request role with no
  clan GUC, ``user_clan_roles_upd`` and ``_del`` are clan-keyed, so the last-admin lock
  reads no row and the explicit role DELETE removes none. The last-admin test answered
  ``assert 200 == 409`` (the clan's only admin was deleted), and the first test's audit row
  read ``{"clan_ids": [], ...}`` (the roles went only by the profile's FK cascade).
- ``lock_clans_where_sole_admin`` replaced by ``[]``: the last-admin test fails on
  ``assert 200 == 409``.
- the ``delete_user`` call removed from the handler: three tests fail, the provider-outage
  one on ``assert 200 == 503``.
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
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import RlsSession, get_db, get_system_db
from app.core.rls import set_request_clan_id
from app.core.security import get_current_user
from app.domain.auth.identity_provider import IdentityUnavailableError
from app.infrastructure.dependencies import get_identity_provider
from app.main import create_app

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


class _FakeIdentity:
    """Records ``delete_user``; ``fail`` makes the provider unreachable."""

    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.fail = False

    async def delete_user(self, user_id: str) -> None:
        if self.fail:
            raise IdentityUnavailableError("provider down")
        self.deleted.append(user_id)


@pytest.fixture()
def identity() -> _FakeIdentity:
    return _FakeIdentity()


@pytest.fixture()
async def http(engine: AsyncEngine, identity: _FakeIdentity) -> AsyncGenerator[AsyncClient]:
    rls_factory = async_sessionmaker(
        engine, sync_session_class=RlsSession, expire_on_commit=False, class_=AsyncSession
    )
    system_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with rls_factory() as session:
            yield session

    async def _override_system_db() -> AsyncGenerator[AsyncSession]:
        async with system_factory() as session:
            yield session

    async def _override_current_user(
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        assert authorization is not None, "test client must send an Authorization header"
        return {"sub": authorization.removeprefix("Bearer ")}

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_system_db] = _override_system_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_identity_provider] = lambda: identity

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


# ── seed + read helpers (privileged connection) ──────────────────────────────


async def _clan(engine: AsyncEngine) -> uuid.UUID:
    cid = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :s)"),
            {"id": cid, "n": f"Họ {cid.hex[:4]}", "s": f"acct-{cid.hex[:10]}"},
        )
    return cid


async def _user(engine: AsyncEngine, *, person_id: uuid.UUID | None = None) -> uuid.UUID:
    uid = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name, person_id) "
                "VALUES (:id, :e, 'Người Dùng', :p)"
            ),
            {"id": uid, "e": f"acct-{uid.hex[:10]}@example.com", "p": person_id},
        )
        await conn.execute(
            sa.text(
                "INSERT INTO user_fcm_tokens (user_id, token, device_platform) "
                "VALUES (:u, :t, 'web')"
            ),
            {"u": uid, "t": f"tok-{uid.hex}"},
        )
    return uid


async def _role(
    engine: AsyncEngine, clan_id: uuid.UUID, user_id: uuid.UUID, role: str, approved: bool = True
) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(id, clan_id, user_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:id, :c, :u, :r, :a, CASE WHEN :a THEN :u END, "
                "CASE WHEN :a THEN now() END)"
            ),
            {"id": uuid.uuid4(), "c": clan_id, "u": user_id, "r": role, "a": approved},
        )


async def _person(engine: AsyncEngine, clan_id: uuid.UUID) -> uuid.UUID:
    pid = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
                "VALUES (:id, 'Nguyễn Văn Liên Kết', 'male', :c, :c)"
            ),
            {"id": pid, "c": clan_id},
        )
        await conn.execute(
            sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
            {"p": pid, "c": clan_id},
        )
    return pid


async def _count(engine: AsyncEngine, sql: str, **params: Any) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(sa.text(sql), params)).scalar_one())


async def _rows_of(engine: AsyncEngine, user_id: uuid.UUID) -> dict[str, int]:
    return {
        "profile": await _count(
            engine, "SELECT count(*) FROM user_profiles WHERE id = :u", u=user_id
        ),
        "roles": await _count(
            engine, "SELECT count(*) FROM user_clan_roles WHERE user_id = :u", u=user_id
        ),
        "tokens": await _count(
            engine, "SELECT count(*) FROM user_fcm_tokens WHERE user_id = :u", u=user_id
        ),
    }


def _auth(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_id}"}


# ── the readings ──────────────────────────────────────────────────────────────


async def test_deleting_an_account_removes_the_provider_user_roles_profile_and_audits_it(
    engine: AsyncEngine, http: AsyncClient, identity: _FakeIdentity
) -> None:
    """The end state of #333's first bullet, read row by row. The user is an editor in
    one clan and pending in another, so both kinds of membership are on trial, and is
    linked to a person, who must stay: the person is the clan's data."""
    clan_a, clan_b = await _clan(engine), await _clan(engine)
    admin_a, admin_b = await _user(engine), await _user(engine)
    await _role(engine, clan_a, admin_a, "admin")
    await _role(engine, clan_b, admin_b, "admin")
    linked = await _person(engine, clan_a)
    user = await _user(engine, person_id=linked)
    await _role(engine, clan_a, user, "editor")
    await _role(engine, clan_b, user, "viewer", approved=False)

    # The premise: the rows exist before the request.
    assert await _rows_of(engine, user) == {"profile": 1, "roles": 2, "tokens": 1}

    resp = await http.delete("/api/v1/auth/me", headers=_auth(user))

    assert resp.status_code == 200, resp.text
    assert set(resp.json()) == {"data"}
    assert identity.deleted == [str(user)]
    assert await _rows_of(engine, user) == {"profile": 0, "roles": 0, "tokens": 0}

    # Nobody else's rows moved, and the linked person is still in the tree.
    assert await _rows_of(engine, admin_a) == {"profile": 1, "roles": 1, "tokens": 1}
    assert await _rows_of(engine, admin_b) == {"profile": 1, "roles": 1, "tokens": 1}
    assert (
        await _count(
            engine, "SELECT count(*) FROM persons WHERE id = :p AND NOT is_deleted", p=linked
        )
        == 1
    )

    async with engine.connect() as conn:
        audit = (
            await conn.execute(
                sa.text(
                    "SELECT actor_id, clan_id, resource_id, old_value, new_value::text "
                    "FROM audit_logs WHERE action = 'account.delete' AND actor_id = :u"
                ),
                {"u": user},
            )
        ).one()
    assert audit.actor_id == user
    assert audit.resource_id == user
    assert audit.clan_id is None
    assert audit.old_value is None
    # The erased data is not copied into the append-only trail.
    assert f"acct-{user.hex[:10]}@example.com" not in audit.new_value
    assert "Người Dùng" not in audit.new_value
    assert str(clan_a) in audit.new_value and str(clan_b) in audit.new_value


async def test_the_last_admin_of_a_clan_is_refused_and_nothing_is_deleted(
    engine: AsyncEngine, http: AsyncClient, identity: _FakeIdentity
) -> None:
    """Refusal must name the clan to transfer, and must leave the account whole: no
    provider call, no row removed, no audit row."""
    clan = await _clan(engine)
    user = await _user(engine)
    await _role(engine, clan, user, "admin")
    editor = await _user(engine)
    await _role(engine, clan, editor, "editor")

    resp = await http.delete("/api/v1/auth/me", headers=_auth(user))

    assert resp.status_code == 409, resp.text
    error = resp.json()["error"]
    assert error["code"] == "account.last_admin_transfer_first"
    assert [c["clan_id"] for c in error["detail"]["clans"]] == [str(clan)]
    assert identity.deleted == []
    assert await _rows_of(engine, user) == {"profile": 1, "roles": 1, "tokens": 1}
    assert (
        await _count(
            engine,
            "SELECT count(*) FROM audit_logs WHERE action = 'account.delete' AND actor_id = :u",
            u=user,
        )
        == 0
    )


async def test_an_admin_with_a_co_admin_may_delete_and_the_clan_keeps_one(
    engine: AsyncEngine, http: AsyncClient, identity: _FakeIdentity
) -> None:
    """The other side of the refusal, so a rule that refused every admin fails here."""
    clan = await _clan(engine)
    user, other = await _user(engine), await _user(engine)
    await _role(engine, clan, user, "admin")
    await _role(engine, clan, other, "admin")

    resp = await http.delete("/api/v1/auth/me", headers=_auth(user))

    assert resp.status_code == 200, resp.text
    assert identity.deleted == [str(user)]
    assert (
        await _count(
            engine,
            "SELECT count(*) FROM user_clan_roles WHERE clan_id = :c AND role = 'admin' "
            "AND is_approved",
            c=clan,
        )
        == 1
    )


async def test_a_provider_failure_leaves_every_row_in_place(
    engine: AsyncEngine, http: AsyncClient, identity: _FakeIdentity
) -> None:
    """The provider call comes before the commit, so an outage rolls the rows back and
    the person can retry, rather than losing their memberships while keeping a sign-in
    account that leads nowhere."""
    clan = await _clan(engine)
    user = await _user(engine)
    await _role(engine, clan, user, "viewer")
    identity.fail = True

    resp = await http.delete("/api/v1/auth/me", headers=_auth(user))

    assert resp.status_code == 503, resp.text
    assert await _rows_of(engine, user) == {"profile": 1, "roles": 1, "tokens": 1}
