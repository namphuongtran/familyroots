"""The status a client is told about an invitation must agree with its ``expires_at`` (S-019).

**The security half was already right before this module existed** and these tests keep it
that way: ``Invitation.accept`` (``app/domain/invitation/entity.py``) refuses a timed-out
invitation with ``invitation.expired``, so an expired invitation cannot be used. The defect
S-019 closed is narrower and is entirely about the answer a reader gets. Nothing sweeps
``clan_invitations`` — a timed-out row keeps ``status = 'pending'`` in storage until the next
create for that (clan, email) lazily retires it (``expire_stale_pending``) — so
``GET /clans/{clan_id}/invitations`` used to report ``pending`` for a link ``accept`` already
refused. An admin would sit waiting on a dead invitation.

**What these tests assert is the response body**, over HTTP, against a real Postgres, and each
one re-reads the stored column with privileged SQL afterwards. That second read is the point:
it proves the reported ``expired`` came from the READ deriving it, and not from something
having quietly rewritten the row. A test that only read the body would pass identically under
a background sweep, which is the other shape S-019 rejected.

**The failing reading differs from the passing one**, which is the second question
``.claude/rules/seeds.md`` § "A test pins an outcome, not a setting" asks: a live pending
still reports ``pending`` (``test_a_live_pending_is_still_reported_pending``), so ``expired``
is not simply what this endpoint now says about everything.

**What this module is NOT evidence about.** It overrides ``get_db`` with the plain session
maker, exactly as ``tests/integration/test_clan_export_json.py`` does, so the RLS seam never
fires here and nothing below proves anything about the ``clan_invitations`` policy.
``test_the_derived_status_did_not_widen_the_clan_filter`` proves the APPLICATION-layer
``WHERE clan_id`` filter — which ``backend/CLAUDE.md`` names the primary guarantee — and
nothing more. The database-layer, two-sided proof for this table is
``tests/integration/test_rls_phase7_clan_invitations.py``, which asserts with naked SQL under
the request role and is unaffected by this change.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db, get_system_db
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """The Authorization header carries ``<user_id>:<email>`` instead of a signed token.

    Only JWT *verification* is stubbed; the profile lookup, the clan resolution and the
    role check below it all run for real against the seeded rows.
    """
    assert authorization is not None, "test client must send an Authorization header"
    raw = authorization.removeprefix("Bearer ")
    user_id, _, email = raw.partition(":")
    return {"sub": user_id, "email": email, "user_metadata": {"full_name": "Test"}}


@pytest.fixture()
async def session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    # ADR-048: accept resolves its handler from ``get_system_db``, not ``get_db``, so a test
    # that drives the accept route has to override BOTH or it reaches the real engine.
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_system_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def _insert_invitation(
    session: AsyncSession,
    *,
    clan_id: uuid.UUID,
    inviter: uuid.UUID,
    email: str,
    token: str,
    expires_at: datetime,
    status: str,
) -> uuid.UUID:
    invitation_id = uuid.uuid4()
    await session.execute(
        sa.text(
            "INSERT INTO clan_invitations "
            "(id, clan_id, email, role, invited_by, token, expires_at, status) "
            "VALUES (:id, :c, :e, 'viewer', :ib, :t, :exp, :st)"
        ),
        {
            "id": invitation_id,
            "c": clan_id,
            "e": email,
            "ib": inviter,
            "t": token,
            "exp": expires_at,
            "st": status,
        },
    )
    return invitation_id


@pytest.fixture()
async def seeded(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """Two clans, an admin in each, and one invitation per case under test.

    Every row is inserted with raw SQL at a chosen ``status``/``expires_at`` pair, so the
    stored value is fixed by the test rather than by whatever the create path happens to do.
    """
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    admin_a, admin_b = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex[:8]

    emails = {
        "timed_out": f"timed-out-{suffix}@example.com",
        "live": f"live-{suffix}@example.com",
        "accepted": f"accepted-{suffix}@example.com",
        "revoked": f"revoked-{suffix}@example.com",
        "stored_expired": f"stored-expired-{suffix}@example.com",
        "clan_b_only": f"clan-b-{suffix}@example.com",
    }
    tokens = {key: f"tok-{key}-{suffix}" for key in emails}

    async with session_factory() as s:
        for clan_id, name in ((clan_a, "Họ A"), (clan_b, "Họ B")):
            await s.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :slug)"),
                {"id": clan_id, "n": name, "slug": f"c-{clan_id.hex[:8]}"},
            )
        for uid, cid in ((admin_a, clan_a), (admin_b, clan_b)):
            await s.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name) "
                    "VALUES (:id, :email, 'Admin')"
                ),
                {"id": uid, "email": f"{uid.hex[:8]}@example.com"},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:uid, :cid, 'admin', true, :uid, now())"
                ),
                {"uid": uid, "cid": cid},
            )

        # Clan A: one row per case. Stored status vs expires_at is the whole subject.
        for key, status, expires_at in (
            ("timed_out", "pending", now - timedelta(days=1)),
            ("live", "pending", now + timedelta(days=7)),
            ("accepted", "accepted", now - timedelta(days=3)),
            ("revoked", "revoked", now - timedelta(days=3)),
            ("stored_expired", "expired", now - timedelta(days=5)),
        ):
            await _insert_invitation(
                s,
                clan_id=clan_a,
                inviter=admin_a,
                email=emails[key],
                token=tokens[key],
                expires_at=expires_at,
                status=status,
            )
        # Clan B holds a timed-out pending too, so the isolation check is not comparing
        # a populated clan against an empty one.
        await _insert_invitation(
            s,
            clan_id=clan_b,
            inviter=admin_b,
            email=emails["clan_b_only"],
            token=tokens["clan_b_only"],
            expires_at=now - timedelta(days=1),
            status="pending",
        )
        await s.commit()

    return {
        "clan_a": clan_a,
        "clan_b": clan_b,
        "admin_a": admin_a,
        "admin_b": admin_b,
        "emails": emails,
        "tokens": tokens,
    }


def _headers(user_id: uuid.UUID, clan_id: uuid.UUID) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {user_id}:{user_id.hex[:8]}@example.com",
        "X-Current-Clan-Id": str(clan_id),
    }


async def _list(client: AsyncClient, seeded: dict[str, Any], who: str) -> dict[str, str]:
    """The list endpoint's response body, reduced to ``{email: status}``."""
    clan = seeded["clan_a"] if who == "a" else seeded["clan_b"]
    admin = seeded["admin_a"] if who == "a" else seeded["admin_b"]
    resp = await client.get(f"/api/v1/clans/{clan}/invitations", headers=_headers(admin, clan))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"data"}, body
    return {row["email"]: row["status"] for row in body["data"]}


async def _stored_status(
    session_factory: async_sessionmaker[AsyncSession], token: str
) -> str | None:
    """The status column as the database actually holds it, read privileged."""
    async with session_factory() as s:
        return (
            await s.execute(
                sa.text("SELECT status FROM clan_invitations WHERE token = :t"), {"t": token}
            )
        ).scalar_one_or_none()


async def test_a_timed_out_invitation_is_reported_expired_not_pending(
    client: AsyncClient,
    seeded: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The defect, watched in the response body.

    RED before S-019: the body says ``pending``, because the route reported the stored
    column verbatim.
    """
    by_email = await _list(client, seeded, "a")

    assert by_email[seeded["emails"]["timed_out"]] == "expired"
    # And the row was NOT rewritten: the report is derived, not swept.
    assert await _stored_status(session_factory, seeded["tokens"]["timed_out"]) == "pending"


async def test_a_live_pending_is_still_reported_pending(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    """The control that makes the test above mean something.

    If this said ``expired`` too, the passing reading and the failing reading would be the
    same value and neither would pin anything.
    """
    by_email = await _list(client, seeded, "a")

    assert by_email[seeded["emails"]["live"]] == "pending"


async def test_terminal_statuses_are_reported_verbatim_past_expiry(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    """Only ``pending`` derives.

    ``accepted`` and ``revoked`` record what a person did. The clock passing afterwards
    does not undo it, and a list that relabelled an accepted invitation ``expired`` would
    tell an admin the member never joined.
    """
    by_email = await _list(client, seeded, "a")
    emails = seeded["emails"]

    assert by_email[emails["accepted"]] == "accepted"
    assert by_email[emails["revoked"]] == "revoked"
    assert by_email[emails["stored_expired"]] == "expired"


async def test_the_derived_status_did_not_widen_the_clan_filter(
    client: AsyncClient,
    seeded: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Both directions, at the application layer: A sees only A's row, B only B's.

    Deriving a field is not supposed to change which rows come back, and a one-sided check
    would miss a filter that had quietly gone away. The database-layer proof for this table
    is ``test_rls_phase7_clan_invitations.py``; see this module's docstring.
    """
    emails = seeded["emails"]
    a_body = await _list(client, seeded, "a")
    b_body = await _list(client, seeded, "b")

    assert emails["timed_out"] in a_body
    assert emails["clan_b_only"] not in a_body
    assert emails["clan_b_only"] in b_body
    assert emails["timed_out"] not in b_body
    # Both rows really are in the table, so "not in" is a filter and not an empty database.
    assert await _stored_status(session_factory, seeded["tokens"]["clan_b_only"]) == "pending"
    assert await _stored_status(session_factory, seeded["tokens"]["timed_out"]) == "pending"


async def test_accept_still_refuses_a_timed_out_invitation(
    client: AsyncClient,
    seeded: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The half that was already right, re-checked AFTER the derived-status change.

    A careless derivation could have taught the read path to report ``expired`` while
    leaving ``accept`` reachable, or the reverse. Both halves now read one predicate
    (``app.domain.invitation.entity.is_expired``); this asserts the accept half still ends
    at 409 ``invitation.expired`` in the response body.
    """
    invitee = uuid.uuid4()
    token = seeded["tokens"]["timed_out"]

    resp = await client.post(
        f"/api/v1/invitations/{token}/accept",
        headers={"Authorization": f"Bearer {invitee}:{seeded['emails']['timed_out']}"},
    )

    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "invitation.expired"
    # Nothing was granted and nothing was written.
    assert await _stored_status(session_factory, token) == "pending"
    async with session_factory() as s:
        granted = (
            await s.execute(
                sa.text("SELECT count(*) FROM user_clan_roles WHERE user_id = :u"),
                {"u": invitee},
            )
        ).scalar_one()
    assert granted == 0
