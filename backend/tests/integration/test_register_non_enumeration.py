"""Register is non-enumerating (ADR-021): identical response whether or not the
email already has an account; existing accounts get a recovery-email nudge."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Iterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.auth.handlers import AuthCommandHandler
from app.core.database import get_db
from app.domain.auth.identity_provider import IdentityUserExistsError
from app.infrastructure.dependencies import get_identity_provider
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.auth_repository import (
    SqlAlchemyAuthQueryPort,
    SqlAlchemyAuthRepository,
)
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.main import create_app

pytestmark = pytest.mark.integration

REGISTER_BODY_NEW = {
    "email": "moi@example.com",
    "password": "S3cure!pass",
    "full_name": "Người Mới",
    "clan_action": "create",
    "clan_name": "Họ Mới",
    "clan_slug": "ho-moi",
}


def _fresh_body(**overrides: Any) -> dict[str, Any]:
    """A REGISTER_BODY_NEW variant with a unique email/slug, so tests that each
    perform a *fresh* registration don't collide on clan-slug uniqueness within
    the session-scoped test database shared across integration modules."""
    uid = uuid.uuid4().hex[:8]
    body = {**REGISTER_BODY_NEW, "email": f"moi-{uid}@example.com", "clan_slug": f"ho-moi-{uid}"}
    body.update(overrides)
    return body


class FakeIdentityProvider:
    """Minimal IdentityProvider stub for the register route.

    Tracks *successful* create_user calls and send_password_reset calls per
    email, so tests can assert "nothing was created" / "the nudge fired"
    independent of HTTP response shape.
    """

    def __init__(self) -> None:
        self._existing: set[str] = set()
        self._create_calls: dict[str, int] = {}
        self._reset_calls: dict[str, int] = {}
        self.fail_password_reset = False

    def seed_existing(self, email: str) -> None:
        self._existing.add(email)

    async def create_user(self, *, email: str, password: str) -> str:
        if email in self._existing:
            raise IdentityUserExistsError(email)
        self._existing.add(email)
        self._create_calls[email] = self._create_calls.get(email, 0) + 1
        return str(uuid.uuid4())

    async def delete_user(self, user_id: str) -> None:
        return None

    async def send_verification_email(self, *, email: str) -> None:
        return None

    async def send_password_reset(self, *, email: str) -> None:
        self._reset_calls[email] = self._reset_calls.get(email, 0) + 1
        if self.fail_password_reset:
            raise RuntimeError("smtp down (simulated)")

    def create_user_calls_for(self, email: str) -> int:
        return self._create_calls.get(email, 0)

    def password_reset_calls_for(self, email: str) -> int:
        return self._reset_calls.get(email, 0)


@pytest.fixture()
def identity_fake() -> FakeIdentityProvider:
    return FakeIdentityProvider()


@pytest.fixture()
def seeded_existing_email(identity_fake: FakeIdentityProvider) -> str:
    email = f"existing-{uuid.uuid4().hex[:8]}@example.com"
    identity_fake.seed_existing(email)
    return email


@pytest.fixture()
def taken_slug(client: TestClient) -> str:
    """A slug that genuinely belongs to a real clan (seeded via an ordinary
    registration), so the slug-taken check has something real to collide with."""
    uid = uuid.uuid4().hex[:8]
    seed_body = {
        "email": f"seed-{uid}@example.com",
        "password": "S3cure!pass",
        "full_name": "Seed User",
        "clan_action": "create",
        "clan_name": "Seed Clan",
        "clan_slug": f"seed-clan-{uid}",
    }
    resp = client.post("/api/v1/auth/register", json=seed_body)
    assert resp.status_code == 201, resp.text
    return seed_body["clan_slug"]


@pytest.fixture()
async def db_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture()
def client(migrated_db_url: str, identity_fake: FakeIdentityProvider) -> Iterator[TestClient]:
    app = create_app()
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_identity_provider] = lambda: identity_fake
    yield TestClient(app)
    engine.sync_engine.dispose()


async def _count(session: AsyncSession, table: str) -> int:
    result = await session.execute(sa.text(f"SELECT count(*) FROM {table}"))
    return int(result.scalar_one())


def test_both_paths_return_identical_body(
    client: TestClient, identity_fake: FakeIdentityProvider, seeded_existing_email: str
) -> None:
    fresh = client.post("/api/v1/auth/register", json=REGISTER_BODY_NEW)
    dup_body = {**REGISTER_BODY_NEW, "email": seeded_existing_email, "clan_slug": "ho-khac"}
    dup = client.post("/api/v1/auth/register", json=dup_body)
    assert fresh.status_code == dup.status_code == 201
    assert fresh.json() == dup.json()  # byte-identical envelope
    assert set(fresh.json()["data"].keys()) == {"message"}  # no ids leak


@pytest.mark.asyncio
async def test_existing_email_creates_nothing_and_nudges(
    client: TestClient,
    identity_fake: FakeIdentityProvider,
    seeded_existing_email: str,
    db_session: AsyncSession,
) -> None:
    before_users = await _count(db_session, "user_profiles")
    before_clans = await _count(db_session, "clans")
    # A unique clan_slug (not the static REGISTER_BODY_NEW one): clan-input
    # validation now runs unconditionally (see the regression tests below), so
    # reusing a slug another test already claimed in this session-scoped DB
    # would 409 here — unrelated to what this test actually verifies (the
    # existing-email nudge/early-return path).
    resp = client.post("/api/v1/auth/register", json=_fresh_body(email=seeded_existing_email))
    assert resp.status_code == 201
    assert identity_fake.create_user_calls_for(seeded_existing_email) == 0
    assert identity_fake.password_reset_calls_for(seeded_existing_email) == 1
    assert await _count(db_session, "user_profiles") == before_users
    assert await _count(db_session, "clans") == before_clans


def test_nudge_failure_still_returns_same_201(
    client: TestClient, identity_fake: FakeIdentityProvider, seeded_existing_email: str
) -> None:
    identity_fake.fail_password_reset = True
    resp = client.post("/api/v1/auth/register", json=_fresh_body(email=seeded_existing_email))
    assert resp.status_code == 201
    assert set(resp.json()["data"].keys()) == {"message"}


@pytest.mark.asyncio
async def test_new_email_full_flow_still_works(
    client: TestClient, identity_fake: FakeIdentityProvider, db_session: AsyncSession
) -> None:
    body = _fresh_body()
    resp = client.post("/api/v1/auth/register", json=body)
    assert resp.status_code == 201
    assert identity_fake.create_user_calls_for(body["email"]) == 1

    clan = (
        await db_session.execute(
            sa.text("SELECT id FROM clans WHERE slug = :s"), {"s": body["clan_slug"]}
        )
    ).first()
    assert clan is not None


@pytest.mark.asyncio
async def test_onboard_response_unchanged(db_session: AsyncSession) -> None:
    """Regression: this task only changes register()'s return surface — onboard
    still returns the full RegisterResponse (user_id, clan_id, is_approved,
    message), since /auth/onboard's route and _assign_clan_membership are
    untouched (reuses the direct-handler pattern from test_auth_provisioning.py,
    which exercises _assign_clan_membership against the real migrated schema)."""
    repo = SqlAlchemyAuthRepository(db_session)
    uow = SqlAlchemyUnitOfWork(db_session, create_event_dispatcher(db_session))
    handler = AuthCommandHandler(repo, uow, AsyncMock(), SqlAlchemyAuthQueryPort(db_session))

    user_id = uuid.uuid4()
    slug = f"onboard-{user_id.hex[:8]}"
    resp = await handler.onboard_authenticated_user(
        user_id=user_id,
        email=f"{user_id.hex[:8]}@example.com",
        full_name="Onboard User",
        clan_action="create",
        clan_name="Onboard Clan",
        clan_slug=slug,
    )
    assert resp.user_id == user_id
    assert resp.is_approved is True
    assert resp.clan_id is not None
    assert resp.message  # unchanged: still a populated RegisterResponse


# ── Regression: clan-input validation must precede identity lookup ───────────
#
# Bug (empirically reproduced): register() used to run create_user FIRST. The
# existing-email branch returned immediately after the nudge, before any clan
# validation ran; the new-email branch instead proceeded into
# _assign_clan_membership, whose validation errors (422/404/409) surfaced to
# the client. So a bad clan_slug/clan_id combined with a *fresh* email failed
# loudly while the same bad input combined with an *existing* email silently
# succeeded (201) — a status-code oracle for account enumeration, defeating
# ADR-021. The fix hoists clan-INPUT validation to the top of register(),
# unconditionally, before create_user runs, so both paths fail identically.


def test_taken_slug_same_status_both_paths(
    client: TestClient,
    identity_fake: FakeIdentityProvider,
    seeded_existing_email: str,
    taken_slug: str,
) -> None:
    fresh_email = f"fresh-{uuid.uuid4().hex[:8]}@example.com"
    fresh_body = {
        "email": fresh_email,
        "password": "S3cure!pass",
        "full_name": "Fresh User",
        "clan_action": "create",
        "clan_name": "Squatter Clan",
        "clan_slug": taken_slug,
    }
    existing_body = {**fresh_body, "email": seeded_existing_email}

    fresh_resp = client.post("/api/v1/auth/register", json=fresh_body)
    existing_resp = client.post("/api/v1/auth/register", json=existing_body)

    assert fresh_resp.status_code == existing_resp.status_code == 409
    assert fresh_resp.json() == existing_resp.json()
    assert fresh_resp.json()["error"]["code"] == "auth.clan_slug_taken"

    # Validation precedes the provider call: identity.create_user was never
    # invoked, and no recovery nudge was sent, on either path — a bad request
    # is not rewarded with a probe signal.
    assert identity_fake.create_user_calls_for(fresh_email) == 0
    assert identity_fake.create_user_calls_for(seeded_existing_email) == 0
    assert identity_fake.password_reset_calls_for(fresh_email) == 0
    assert identity_fake.password_reset_calls_for(seeded_existing_email) == 0


def test_missing_clan_id_same_status_both_paths(
    client: TestClient,
    identity_fake: FakeIdentityProvider,
    seeded_existing_email: str,
) -> None:
    fresh_email = f"fresh-{uuid.uuid4().hex[:8]}@example.com"
    fresh_body = {
        "email": fresh_email,
        "password": "S3cure!pass",
        "full_name": "Fresh User",
        "clan_action": "join",
        # clan_id intentionally omitted
    }
    existing_body = {**fresh_body, "email": seeded_existing_email}

    fresh_resp = client.post("/api/v1/auth/register", json=fresh_body)
    existing_resp = client.post("/api/v1/auth/register", json=existing_body)

    assert fresh_resp.status_code == existing_resp.status_code == 422
    assert fresh_resp.json() == existing_resp.json()
    assert fresh_resp.json()["error"]["code"] == "auth.clan_id_required_for_join"

    assert identity_fake.create_user_calls_for(fresh_email) == 0
    assert identity_fake.create_user_calls_for(seeded_existing_email) == 0
    assert identity_fake.password_reset_calls_for(fresh_email) == 0
    assert identity_fake.password_reset_calls_for(seeded_existing_email) == 0


def test_nonexistent_clan_join_same_status_both_paths(
    client: TestClient,
    identity_fake: FakeIdentityProvider,
    seeded_existing_email: str,
) -> None:
    random_clan_id = str(uuid.uuid4())
    fresh_email = f"fresh-{uuid.uuid4().hex[:8]}@example.com"
    fresh_body = {
        "email": fresh_email,
        "password": "S3cure!pass",
        "full_name": "Fresh User",
        "clan_action": "join",
        "clan_id": random_clan_id,
    }
    existing_body = {**fresh_body, "email": seeded_existing_email}

    fresh_resp = client.post("/api/v1/auth/register", json=fresh_body)
    existing_resp = client.post("/api/v1/auth/register", json=existing_body)

    assert fresh_resp.status_code == existing_resp.status_code == 404
    assert fresh_resp.json() == existing_resp.json()
    assert fresh_resp.json()["error"]["code"] == "clan_not_found"

    assert identity_fake.create_user_calls_for(fresh_email) == 0
    assert identity_fake.create_user_calls_for(seeded_existing_email) == 0
    assert identity_fake.password_reset_calls_for(fresh_email) == 0
    assert identity_fake.password_reset_calls_for(seeded_existing_email) == 0
