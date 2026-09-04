"""Audit rows written by request routes that have NO clan GUC — migration 034, ADR-043 §§ 2, 6.

This is the file that catches migration ``034`` being wrong, and no unit test can stand in
for it. ADR-038 recorded that its own instance of this bug stayed invisible "until a test
drove an HTTP write through a real ``RlsSession``".

The chain, in four steps:

1. The RLS seam drops to ``familyroots_app`` and writes ``app.clan_id`` on **every**
   transaction of a request session (``app/core/rls.py:63-65``), whether or not a clan is
   known. The GUC is written in exactly one place, ``get_current_clan_id``
   (``app/core/security.py:290``).
2. ``POST /api/v1/auth/register`` is unauthenticated and ``POST /api/v1/auth/onboard`` takes
   ``get_current_user`` only (``app/api/v1/auth.py:44-49``, ``:63-68``), and
   ``app/api/v1/auth.py:17`` imports ``get_current_user`` and nothing else from
   ``app.core.security`` — so no route in that module can have a clan GUC. Both write a
   ``clan.create`` (or ``clan.join_request``) audit row through ``emit_audit_event``
   (``app/application/auth/handlers.py:154``, ``:189``) on the request session.
3. ``audit_logs_ins`` is ``WITH CHECK (true)``, so those inserts are admitted. That is the
   whole reason ADR-043 § 3 refused the migration-027 template here.
4. But ``audit_logs_sel`` is clan-keyed, and Postgres matches a ``RETURNING`` row against the
   **SELECT** policy. With ``eager_defaults="auto"`` — which resolves to True for the
   ``AuditLog`` mapper, because ``created_at`` carries a ``server_default`` — SQLAlchemy would
   append ``RETURNING created_at`` to every insert, the write would be accepted and then the
   row rejected on its way back, and **registration would 500**.

``app/models/audit_log.py`` sets ``__mapper_args__ = {"eager_defaults": False}`` to remove the
read rather than widen the policy, on ADR-038's grounds. The first class below pins the
constraint that fix works *within*; the HTTP tests below it drive the real routes.

**These tests only mean something because ``get_db`` is overridden to a real ``RlsSession``.**
``tests/integration/test_auth_http_flow.py:154-160`` points ``get_db`` at the plain
privileged maker, which is right for what that module measures and useless here — it would
pass with or without migration 034. Each client fixture below therefore probes
``SELECT current_user`` on the session it hands the route and asserts it really is
``familyroots_app``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import RlsSession, get_db, get_system_db
from app.core.rls import set_request_clan_id
from app.core.security import get_current_user
from app.domain.auth.identity_provider import IdentityUserExistsError
from app.infrastructure.dependencies import get_identity_provider
from app.main import create_app
from app.models.audit_log import AuditLog

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


def _rls(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine, sync_session_class=RlsSession, expire_on_commit=False, class_=AsyncSession
    )


def _system(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# ── the constraint the ORM fix works within ──────────────────────────────────


class TestReturningIsStillRejectedByAuditLogsSel:
    """``audit_logs_sel`` is deliberately unchanged, so the collision is still live for any
    write path that asks for a row back. Pinned so a future ``INSERT … RETURNING`` against
    this table, or a removal of ``eager_defaults=False``, fails here with a clear reason
    instead of failing in production on the registration route."""

    async def test_raw_insert_returning_with_no_clan_guc_is_denied(
        self, engine: AsyncEngine
    ) -> None:
        """Both halves in one transaction, so the difference is unmistakably the
        ``RETURNING`` clause and nothing else: the plain INSERT is accepted by
        ``audit_logs_ins``, and the identical INSERT with ``RETURNING created_at`` is
        rejected because the returned row is matched against ``audit_logs_sel``, whose
        predicate is NULL when no clan is selected."""
        rls = _rls(engine)
        set_request_clan_id(None)
        async with rls() as s:
            assert await s.scalar(sa.text("SELECT current_setting('app.clan_id', true)")) == ""

            await s.execute(
                sa.text(
                    "INSERT INTO audit_logs (id, clan_id, actor_id, actor_role, action, "
                    "resource_type) VALUES (:i, NULL, :a, 'admin', 'clan.create', 'clan')"
                ),
                {"i": uuid.uuid4(), "a": uuid.uuid4()},
            )

            with pytest.raises(Exception, match="row-level security"):
                await s.execute(
                    sa.text(
                        "INSERT INTO audit_logs (id, clan_id, actor_id, actor_role, action, "
                        "resource_type) VALUES (:i, NULL, :a, 'admin', 'clan.create', 'clan') "
                        "RETURNING created_at"
                    ),
                    {"i": uuid.uuid4(), "a": uuid.uuid4()},
                )
            await s.rollback()

    async def test_the_orm_insert_emits_no_returning_for_audit_logs(
        self, engine: AsyncEngine
    ) -> None:
        """The mechanical assertion behind the fix, and the one that survives a rewrite of
        everything else: whatever changes, the compiled ``audit_logs`` INSERT must carry no
        RETURNING clause. Mirrors
        ``test_rls_person_create.py::test_the_orm_insert_emits_no_returning_for_persons``."""
        statements: list[str] = []
        rls = _rls(engine)
        set_request_clan_id(None)
        async with rls() as s:
            sync_session = await s.run_sync(lambda sess: sess)

            @event.listens_for(sync_session.get_bind(), "before_cursor_execute")
            def _capture(  # type: ignore[no-untyped-def]
                conn, cursor, statement, parameters, context, executemany
            ) -> None:
                statements.append(statement)

            s.add(
                AuditLog(
                    clan_id=None,
                    actor_id=uuid.uuid4(),
                    actor_role="admin",
                    action="clan.create",
                    resource_type="clan",
                )
            )
            await s.flush()
            await s.rollback()

        inserts = [q for q in statements if "INSERT INTO audit_logs" in q]
        assert inserts, statements
        assert not any("RETURNING" in q.upper() for q in inserts), inserts


# ── the real routes, over HTTP, on a real RlsSession ─────────────────────────


class _StubIdentity:
    """Just enough ``IdentityProvider`` for ``register``. JWT verification is not the
    subject here — ``get_current_user`` is overridden separately — so this mints no tokens."""

    def __init__(self) -> None:
        self.created: dict[str, str] = {}
        self.deleted: list[str] = []
        self.verification_emails: list[str] = []

    async def create_user(self, *, email: str, password: str) -> str:
        if email in self.created:
            raise IdentityUserExistsError(email)
        user_id = str(uuid.uuid4())
        self.created[email] = user_id
        return user_id

    async def delete_user(self, user_id: str) -> None:
        # If a policy rejected the audit write, register compensates through here. The
        # test asserts this list is EMPTY, which is a second, independent signal.
        self.deleted.append(user_id)

    async def send_verification_email(self, *, email: str) -> None:
        self.verification_emails.append(email)

    async def send_password_reset(self, *, email: str) -> None:
        return None


class _Probe:
    """Records the DB role the route actually ran under, so a client accidentally wired to
    the privileged session cannot pass these tests silently."""

    def __init__(self) -> None:
        self.roles: list[str] = []


@pytest.fixture()
async def probe() -> _Probe:
    return _Probe()


@pytest.fixture()
async def identity() -> _StubIdentity:
    return _StubIdentity()


@pytest.fixture()
async def current_user() -> dict[str, Any]:
    """Mutable holder so a test can decide who is calling before it issues the request."""
    return {}


@pytest.fixture()
async def http(
    engine: AsyncEngine,
    probe: _Probe,
    identity: _StubIdentity,
    current_user: dict[str, Any],
) -> AsyncGenerator[AsyncClient]:
    """Production wiring: ``get_db`` on the RLS request session, ``get_system_db``
    privileged. A fresh ``create_app()`` per test keeps the ADR-021 rate-limit bucket
    (20 req/min/IP on ``/api/v1/auth`` and ``/api/v1/invitations``) empty."""
    rls_factory = _rls(engine)
    system_factory = _system(engine)
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with rls_factory() as session:
            # Opens the transaction, which fires the seam; record what it produced. The
            # route then reuses this very session, so this is the role it will write under.
            probe.roles.append(await session.scalar(sa.text("SELECT current_user")) or "")
            yield session

    async def _override_system_db() -> AsyncGenerator[AsyncSession]:
        async with system_factory() as session:
            yield session

    async def _override_current_user(
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        assert authorization is not None, "test client must send an Authorization header"
        return current_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_system_db] = _override_system_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_identity_provider] = lambda: identity

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def _audit_rows(engine: AsyncEngine, clan_id: uuid.UUID) -> list[str]:
    """Read the audit trail from a PRIVILEGED session. Reading it back through the request
    role would be circular here: ``audit_logs_sel`` is exactly what is on trial."""
    async with engine.connect() as conn:
        return list(
            (
                await conn.execute(
                    sa.text("SELECT action FROM audit_logs WHERE clan_id = :c ORDER BY created_at"),
                    {"c": clan_id},
                )
            ).scalars()
        )


async def test_register_writes_its_audit_row_under_the_request_role(
    engine: AsyncEngine, http: AsyncClient, probe: _Probe, identity: _StubIdentity
) -> None:
    """``POST /auth/register`` is unauthenticated, so there is no clan GUC and no way to get
    one. Without ``eager_defaults=False`` this request 500s.

    The 201 alone is not the whole proof: register is non-enumerating (ADR-021) and answers
    with the same uniform message either way, so the audit row is read back privileged and
    ``identity.deleted`` is checked empty — a rejected audit write would have triggered
    register's compensating ``delete_user``.
    """
    slug = f"s014-reg-{uuid.uuid4().hex[:8]}"
    resp = await http.post(
        "/api/v1/auth/register",
        json={
            "email": f"{slug}@example.com",
            "password": "s3cret-pass",
            "full_name": "Người sáng lập",
            "clan_action": "create",
            "clan_name": "S014 Clan",
            "clan_slug": slug,
        },
    )
    assert resp.status_code == 201, resp.text
    assert probe.roles and set(probe.roles) == {"familyroots_app"}, (
        f"the route did not run on the RLS request session (roles seen: {probe.roles}); "
        f"this test proves nothing about migration 034 unless it does"
    )
    assert identity.deleted == [], (
        "register compensated by deleting the auth user, which means the DB half failed — "
        "most likely audit_logs_sel rejecting a RETURNING row"
    )

    async with engine.connect() as conn:
        clan_id = await conn.scalar(sa.text("SELECT id FROM clans WHERE slug = :s"), {"s": slug})
    assert clan_id is not None, "registration did not create the clan"
    assert await _audit_rows(engine, clan_id) == ["clan.create"]


async def test_onboard_writes_its_audit_row_under_the_request_role(
    engine: AsyncEngine, http: AsyncClient, probe: _Probe, current_user: dict[str, Any]
) -> None:
    """``POST /auth/onboard`` takes ``get_current_user`` and no clan dependency, so it is the
    second no-GUC audit writer. Same failure mode, different route."""
    user_id = uuid.uuid4()
    current_user.update(
        {
            "sub": str(user_id),
            "email": f"onboard-{user_id.hex[:8]}@example.com",
            "user_metadata": {"full_name": "Người dùng"},
        }
    )
    slug = f"s014-onb-{uuid.uuid4().hex[:8]}"

    resp = await http.post(
        "/api/v1/auth/onboard",
        json={"clan_action": "create", "clan_name": "S014 Onboard", "clan_slug": slug},
        headers={"Authorization": f"Bearer {user_id}"},
    )
    assert resp.status_code == 201, resp.text
    assert set(probe.roles) == {"familyroots_app"}, probe.roles

    clan_id = uuid.UUID(resp.json()["data"]["clan_id"])
    assert await _audit_rows(engine, clan_id) == ["clan.create"]


async def test_invitation_accept_still_writes_its_audit_row(
    engine: AsyncEngine, http: AsyncClient, current_user: dict[str, Any]
) -> None:
    """ADR-043's Measurement 2 lists this route as a third no-GUC **request-role** audit
    writer. **That is stale, and the code is the truth**: ADR-048 moved accept onto
    ``get_invitation_accept_handler`` (``app/infrastructure/dependencies.py:358-362``), which
    depends on ``get_system_db``. Its audit row is therefore written by the bypassing login
    role, and no policy applies to it at all.

    The route is still driven here for two reasons. It is the one place the audit row could
    silently stop being written if someone re-pointed the provider at ``get_db`` — the
    ``clan_invitations`` policy would then hide the invitation and accept would 404 before
    ever reaching the audit write. And it confirms the two remaining no-GUC writers above are
    the complete list, rather than leaving a reader to assume ADR-043's three still holds.

    Note the ``get_system_db`` override in the client fixture: without it this route reaches
    the real engine, which is the trap ``backend/CLAUDE.md`` records for the claim routes.
    """
    clan_id, invitee = uuid.uuid4(), uuid.uuid4()
    token = f"tok-{uuid.uuid4().hex}"
    email = f"{invitee.hex[:12]}@example.com"
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
            {"id": clan_id, "s": f"c{clan_id.hex[:10]}"},
        )
        await conn.execute(
            sa.text(
                "INSERT INTO clan_invitations (id, clan_id, email, role, invited_by, token, "
                "expires_at, status) VALUES (:id, :c, :e, 'editor', :ib, :t, :exp, 'pending')"
            ),
            {
                "id": uuid.uuid4(),
                "c": clan_id,
                "e": email,
                "ib": uuid.uuid4(),
                "t": token,
                "exp": datetime.now(UTC) + timedelta(days=7),
            },
        )

    current_user.update(
        {"sub": str(invitee), "email": email, "user_metadata": {"full_name": "Người được mời"}}
    )
    resp = await http.post(
        f"/api/v1/invitations/{token}/accept", headers={"Authorization": f"Bearer {invitee}"}
    )
    assert resp.status_code == 200, resp.text
    assert await _audit_rows(engine, clan_id) == ["invitation.accept"], (
        "accept stopped writing its audit row — check whether the provider moved back to "
        "get_db, in which case clan_invitations' policy hides the invitation first"
    )
