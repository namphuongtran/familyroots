"""The join path resolves a clan by its **code** (the slug), not by its UUID.

ADR-057 § 2. Every assertion here sends an HTTP request and reads the
response body, or reads the row back from Postgres. None of them asserts that a
schema field exists: a field's presence is a fact the code already guarantees, so
an assertion on it cannot fail for the reason this seed exists (see
``.claude/rules/testing.md`` § "A test pins an outcome, not a setting").

**This module is not evidence about RLS.** ``get_db`` is pointed at the plain
privileged session maker, exactly as ``test_register_non_enumeration.py`` and
``test_auth_http_flow.py`` do, so the ``RlsSession`` seam never fires here. What
the join path does under the non-privileged request role is covered by
``test_rls_login_two_clans.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import get_current_user
from app.infrastructure.dependencies import get_identity_provider
from app.main import create_app

pytestmark = pytest.mark.integration

_PASSWORD = "S3cure!pass"


class _FakeIdentity:
    """Enough IdentityProvider surface for register/onboard, and nothing else.

    ``created`` records the ids handed out so a test can prove the identity was
    never created on a rejected request.
    """

    def __init__(self) -> None:
        self.created: dict[str, str] = {}

    async def create_user(self, *, email: str, password: str) -> str:
        user_id = str(uuid.uuid4())
        self.created[email] = user_id
        return user_id

    async def delete_user(self, user_id: str) -> None:
        return None

    async def send_verification_email(self, *, email: str) -> None:
        return None

    async def send_password_reset(self, *, email: str) -> None:
        return None


@pytest.fixture()
def identity() -> _FakeIdentity:
    return _FakeIdentity()


@pytest.fixture()
def onboarding_user() -> dict[str, Any]:
    """The claim set ``POST /auth/onboard`` reads. Mutated per test via ``["sub"]``."""
    return {
        "sub": str(uuid.uuid4()),
        "email": f"onboard-{uuid.uuid4().hex[:8]}@example.com",
        "user_metadata": {"full_name": "Người Tham Gia"},
    }


@pytest.fixture()
def client(
    migrated_db_url: str, identity: _FakeIdentity, onboarding_user: dict[str, Any]
) -> Iterator[TestClient]:
    app = create_app()
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_identity_provider] = lambda: identity
    app.dependency_overrides[get_current_user] = lambda: onboarding_user
    yield TestClient(app)
    engine.sync_engine.dispose()


@pytest.fixture()
async def db(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed_clan(db: AsyncSession, label: str) -> tuple[uuid.UUID, str]:
    """Insert a clan and return ``(id, code)``. The code is its ``slug``."""
    clan_id = uuid.uuid4()
    code = f"{label}-{clan_id.hex[:10]}"
    await db.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:i, :n, :s)"),
        {"i": clan_id, "n": f"Họ {label}", "s": code},
    )
    await db.commit()
    return clan_id, code


async def _memberships_of(db: AsyncSession, email: str) -> list[tuple[uuid.UUID, bool]]:
    """Every ``user_clan_roles`` row belonging to the profile with this email.

    Read at the database layer on purpose: ``POST /auth/register`` is
    non-enumerating (ADR-021), so its body carries no ids at all and cannot say
    which clan the join actually landed on.
    """
    rows = (
        await db.execute(
            sa.text(
                "SELECT r.clan_id, r.is_approved FROM user_clan_roles r "
                "JOIN user_profiles p ON p.id = r.user_id WHERE p.email = :e"
            ),
            {"e": email},
        )
    ).all()
    return [(row[0], row[1]) for row in rows]


def _register_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "email": f"join-{uuid.uuid4().hex[:8]}@example.com",
        "password": _PASSWORD,
        "full_name": "Người Tham Gia",
        "clan_action": "join",
    }
    body.update(overrides)
    return body


# ── (a) a real code joins, and the membership row appears ─────────────────────


@pytest.mark.asyncio
async def test_register_join_by_code_lands_the_membership_on_that_clan_and_not_the_other(
    client: TestClient, db: AsyncSession
) -> None:
    """Two clans exist; the code names one. Read the row back, both sides.

    The one-sided reading — "a row exists for clan A" — passes just as well if the
    lookup ignored the code and took the first clan it found. The second assertion
    is the half that fails in that case.
    """
    clan_a, code_a = await _seed_clan(db, "a")
    clan_b, _code_b = await _seed_clan(db, "b")

    body = _register_body(clan_code=code_a)
    resp = client.post("/api/v1/auth/register", json=body)
    assert resp.status_code == 201, resp.text
    assert set(resp.json()["data"].keys()) == {"message"}  # ADR-021: still no ids

    rows = await _memberships_of(db, body["email"])
    assert rows == [(clan_a, False)], rows
    assert clan_b not in [clan_id for clan_id, _ in rows]


@pytest.mark.asyncio
async def test_onboard_join_by_code_answers_with_the_clan_the_code_names(
    client: TestClient, db: AsyncSession, onboarding_user: dict[str, Any]
) -> None:
    """``POST /auth/onboard`` keeps the full ``RegisterResponse``, so here the
    resolved clan is readable straight off the response body."""
    clan_a, code_a = await _seed_clan(db, "onb")
    await _seed_clan(db, "onbother")

    resp = client.post(
        "/api/v1/auth/onboard",
        headers={"Authorization": "Bearer x"},
        json={"clan_action": "join", "clan_code": code_a},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["clan_id"] == str(clan_a), data
    assert data["is_approved"] is False, data

    rows = await _memberships_of(db, onboarding_user["email"])
    assert rows == [(clan_a, False)], rows


# ── (b) an unknown code answers clan_not_found ────────────────────────────────


def test_register_with_an_unknown_code_answers_clan_not_found(client: TestClient) -> None:
    """Well-formed, and no clan carries it. Spec § 7.1b writes this copy."""
    resp = client.post(
        "/api/v1/auth/register", json=_register_body(clan_code=f"khong-co-{uuid.uuid4().hex[:8]}")
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "clan_not_found", resp.text


def test_onboard_with_an_unknown_code_answers_clan_not_found(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/onboard",
        headers={"Authorization": "Bearer x"},
        json={"clan_action": "join", "clan_code": f"khong-co-{uuid.uuid4().hex[:8]}"},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "clan_not_found", resp.text


@pytest.mark.asyncio
async def test_an_unknown_code_creates_no_identity_and_no_membership(
    client: TestClient, db: AsyncSession, identity: _FakeIdentity
) -> None:
    """ADR-021's ordering still holds for the code path: clan-input validation
    runs before ``create_user``, so a bad code leaves nothing behind."""
    body = _register_body(clan_code=f"khong-co-{uuid.uuid4().hex[:8]}")
    resp = client.post("/api/v1/auth/register", json=body)
    assert resp.status_code == 404, resp.text
    assert identity.created == {}
    assert await _memberships_of(db, body["email"]) == []


# ── (c) a code failing _SLUG_PATTERN is rejected at the door ──────────────────


@pytest.mark.parametrize(
    "bad_code",
    [
        "Nguyen-Huu",  # uppercase
        "nguyen huu",  # space
        "-nguyen",  # leading hyphen
        "nguyen--huu",  # doubled hyphen
        "nguyễn-hữu",  # non-ASCII
        "",  # empty
    ],
)
def test_a_code_failing_the_slug_pattern_never_reaches_the_lookup(
    client: TestClient, identity: _FakeIdentity, bad_code: str
) -> None:
    """Rejected *at the door* means the framework's ``validation_error``, naming
    ``body.clan_code`` — not the handler's 404 ``clan_not_found``.

    The two readings differ, which is the point: a 404 here would mean the badly
    shaped string was carried all the way into a database lookup.
    """
    resp = client.post("/api/v1/auth/register", json=_register_body(clan_code=bad_code))
    assert resp.status_code == 422, resp.text
    error = resp.json()["error"]
    assert error["code"] == "validation_error", resp.text
    assert "body.clan_code" in error["detail"]["fields"], resp.text
    assert identity.created == {}


def test_onboard_rejects_a_badly_shaped_code_at_the_door(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/onboard",
        headers={"Authorization": "Bearer x"},
        json={"clan_action": "join", "clan_code": "Nguyen Huu"},
    )
    assert resp.status_code == 422, resp.text
    error = resp.json()["error"]
    assert error["code"] == "validation_error", resp.text
    assert "body.clan_code" in error["detail"]["fields"], resp.text


# ── The deprecation window this seed decided, per docs/contracts/rest-auth-api.md


@pytest.mark.asyncio
async def test_clan_id_still_joins_for_one_release(client: TestClient, db: AsyncSession) -> None:
    """The contract accepts ``clan_id`` alongside ``clan_code`` for one release, so
    the web form keeps working until it is rewritten. Delete this test with the field."""
    clan_a, _code_a = await _seed_clan(db, "legacy")
    body = _register_body(clan_id=str(clan_a))
    resp = client.post("/api/v1/auth/register", json=body)
    assert resp.status_code == 201, resp.text
    assert await _memberships_of(db, body["email"]) == [(clan_a, False)]


@pytest.mark.asyncio
async def test_sending_both_identifiers_is_refused_by_name(
    client: TestClient, db: AsyncSession, identity: _FakeIdentity
) -> None:
    """Two identifiers that can disagree must never be silently reconciled: the
    request names one clan and the join must land on the clan it named."""
    clan_a, _code_a = await _seed_clan(db, "botha")
    _clan_b, code_b = await _seed_clan(db, "bothb")

    body = _register_body(clan_id=str(clan_a), clan_code=code_b)
    resp = client.post("/api/v1/auth/register", json=body)
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "auth.clan_code_and_id_both_given", resp.text
    assert identity.created == {}
    assert await _memberships_of(db, body["email"]) == []


def test_join_with_neither_identifier_still_answers_the_documented_code(
    client: TestClient,
) -> None:
    """``auth.clan_id_required_for_join`` keeps its name through the window. Spec
    § 7.1b names it and ``docs/contracts/error-codes.md`` documents it; renaming a
    stable error code would be a second breaking change for no gain."""
    resp = client.post("/api/v1/auth/register", json=_register_body())
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "auth.clan_id_required_for_join", resp.text
