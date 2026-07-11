"""HTTP-level auth smoke suite: the full request path over a real migrated DB.

Covers the exact layers where the 2026-07-03 e2e bugs (#12/#13) hid — the DI
graph, the error envelope, and the read-model mapping — by driving the app
through TestClient instead of calling handlers directly:

    register → login → /auth/me → /me/clans → create person

The external identity provider is the only stubbed seam, swapped via
``app.dependency_overrides[get_identity_provider]``. JWT *verification* is NOT
bypassed: the stub mints RS256 tokens signed with a test keypair whose public
JWK is injected into the JWKS cache, so ``verify_supabase_token`` runs for real
(algorithm selection, audience, issuer, expiry).
"""

import time
import uuid
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwk, jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.security as security_module
from app.core.database import get_db
from app.domain.auth.identity_provider import (
    AuthenticatedIdentity,
    AuthTokens,
    IdentityAuthError,
    IdentityEmailNotVerifiedError,
    IdentityUserExistsError,
)
from app.infrastructure.dependencies import get_identity_provider
from app.main import create_app

_KID = "test-key-1"


@pytest.fixture(scope="module")
def rsa_keys() -> dict[str, Any]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    public_jwk = jwk.construct(public_pem, "RS256").to_dict()
    public_jwk.update({"kid": _KID, "use": "sig", "alg": "RS256"})
    return {"private_pem": private_pem, "jwks": {"keys": [public_jwk]}}


@pytest.fixture(scope="module")
def jwks_cache(rsa_keys: dict[str, Any]) -> Iterator[None]:
    """Prime the JWKS cache with the test public key so token verification runs
    the real code path without a network fetch."""
    old_cache, old_time = security_module._jwks_cache, security_module._jwks_cache_time
    security_module._jwks_cache = rsa_keys["jwks"]
    security_module._jwks_cache_time = time.monotonic()
    yield
    security_module._jwks_cache, security_module._jwks_cache_time = old_cache, old_time


def _issuer() -> str:
    # Must match what verify_supabase_token derives from the settings object it
    # actually holds (module-level import), whatever .env says.
    return f"{security_module.settings.SUPABASE_URL.rstrip('/')}/auth/v1"  # type: ignore[attr-defined]


class StubIdentityProvider:
    """In-memory IdentityProvider that mints verifiable RS256 JWTs."""

    def __init__(self, private_pem: str) -> None:
        self._private_pem = private_pem
        self._users: dict[str, dict[str, str]] = {}  # email -> {id, password, full_name}
        self.verification_emails: list[str] = []

    def _mint(self, user_id: str, email: str, full_name: str) -> str:
        now = datetime.now(UTC)
        claims = {
            "sub": user_id,
            "email": email,
            "aud": "authenticated",
            "iss": _issuer(),
            "iat": now,
            "exp": now + timedelta(hours=1),
            "user_metadata": {"full_name": full_name},
        }
        return jwt.encode(claims, self._private_pem, algorithm="RS256", headers={"kid": _KID})

    async def create_user(self, *, email: str, password: str) -> str:
        if email in self._users:
            raise IdentityUserExistsError(email)
        user_id = str(uuid.uuid4())
        self._users[email] = {"id": user_id, "password": password, "full_name": ""}
        return user_id

    async def delete_user(self, user_id: str) -> None:
        self._users = {e: u for e, u in self._users.items() if u["id"] != user_id}

    async def sign_in(self, *, email: str, password: str) -> AuthenticatedIdentity:
        user = self._users.get(email)
        if user is None or user["password"] != password:
            raise IdentityAuthError("invalid credentials")
        access = self._mint(user["id"], email, user["full_name"])
        return AuthenticatedIdentity(
            user_id=user["id"],
            email=email,
            full_name=user["full_name"],
            tokens=AuthTokens(access_token=access, refresh_token="stub-refresh", expires_in=3600),
        )

    async def refresh(self, *, refresh_token: str) -> AuthTokens:
        if refresh_token != "stub-refresh":
            raise IdentityAuthError("bad refresh token")
        return AuthTokens(access_token="new-access", refresh_token="stub-refresh", expires_in=3600)

    async def sign_out(self, *, access_token: str) -> None:
        return None

    async def update_user(
        self, *, user_id: str, full_name: str | None, preferred_locale: str | None
    ) -> None:
        return None

    async def send_verification_email(self, *, email: str) -> None:
        self.verification_emails.append(email)


@pytest.fixture(scope="module")
def stub_identity(rsa_keys: dict[str, Any]) -> StubIdentityProvider:
    return StubIdentityProvider(rsa_keys["private_pem"])


@pytest.fixture(scope="module")
def client(
    migrated_db_url: str, stub_identity: StubIdentityProvider, jwks_cache: None
) -> Iterator[TestClient]:
    app = create_app()
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_identity_provider] = lambda: stub_identity
    # No context manager: lifespan (Sentry/Firebase/scheduler/migration check)
    # must stay out of scope — this suite tests the request path only.
    #
    # Budget note: RateLimitMiddleware allows 20 req/min/IP on /api/v1/auth and
    # this app instance is shared module-wide — currently ~15 auth-path requests.
    # Hitting mysterious 429s after adding tests? You've spent the budget.
    yield TestClient(app)
    engine.sync_engine.dispose()


def _register(client: TestClient, email: str, password: str, slug: str) -> dict[str, Any]:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Smoke Founder",
            "clan_action": "create",
            "clan_name": "Smoke Clan",
            "clan_slug": slug,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body.keys()) == {"data"}  # enveloped
    result: dict[str, Any] = body["data"]
    return result


@pytest.fixture(scope="module")
def founder(client: TestClient) -> dict[str, Any]:
    """A registered clan founder for the negative tests, so each of them is
    self-contained (runnable via -k) instead of depending on the happy path.
    Identifiers are unique per run — the migrated DB is session-scoped and
    shared with other integration modules."""
    email = f"smoke-founder-{uuid.uuid4().hex[:8]}@example.com"
    password = "s3cret-pass"
    slug = f"smoke-clan-{uuid.uuid4().hex[:8]}"
    reg = _register(client, email, password, slug)
    return {"email": email, "password": password, "clan_id": reg["clan_id"], "clan_slug": slug}


# ── Happy path: the full flow that hid #12/#13 ────────────────────


def test_register_login_me_clans_create_person(client: TestClient) -> None:
    email = f"smoke-flow-{uuid.uuid4().hex[:8]}@example.com"
    password = "s3cret-pass"

    # Register, creating a clan → approved admin membership.
    reg = _register(client, email, password, f"smoke-flow-{uuid.uuid4().hex[:8]}")
    assert reg["is_approved"] is True
    clan_id = reg["clan_id"]

    # Login — exercises the CQRS login-profile read model (the seam of #13).
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"data"}  # enveloped
    login = body["data"]
    token = login["access_token"]
    assert login["user"]["clan_id"] == clan_id
    assert login["user"]["role"] == "admin"
    assert login["user"]["is_approved"] is True

    auth = {"Authorization": f"Bearer {token}"}

    # /auth/me — real JWT verification + profile projection + {"data"} envelope.
    resp = client.get("/api/v1/auth/me", headers=auth)
    assert resp.status_code == 200, resp.text
    me = resp.json()["data"]
    assert me["email"] == email
    assert me["clan_id"] == clan_id

    # /me/clans — membership projection, enveloped as {"data": [...], "meta": {"count": n}}.
    resp = client.get("/api/v1/me/clans", headers=auth)
    assert resp.status_code == 200, resp.text
    clans = resp.json()
    assert clans["meta"]["count"] == 1
    assert clans["data"][0]["clan_id"] == clan_id
    assert clans["data"][0]["role"] == "admin"

    # Create a person — clan auto-selection + RBAC + UoW write path.
    resp = client.post(
        "/api/v1/persons",
        headers=auth,
        json={"full_name": "Tổ Tiên", "gender": "male"},
    )
    assert resp.status_code == 201, resp.text
    person = resp.json()["data"]
    assert person["full_name"] == "Tổ Tiên"

    # And the explicit clan header must also be honoured.
    resp = client.get("/api/v1/me/clans", headers={**auth, "X-Current-Clan-Id": clan_id})
    assert resp.status_code == 200


def test_refresh_and_logout_are_enveloped(client: TestClient, founder: dict[str, Any]) -> None:
    """Both refresh and logout responses must carry the ``{"data": ...}`` envelope.

    Reuses the shared ``founder`` fixture (rather than a fresh registration) to stay
    within the module's shared rate-limit budget — see the ``client`` fixture note.
    """
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": founder["email"], "password": founder["password"]},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]

    r = client.post("/api/v1/auth/refresh", json={"refresh_token": "stub-refresh"})
    assert r.status_code == 200, r.text
    r_body = r.json()
    assert set(r_body.keys()) == {"data"}
    assert "access_token" in r_body["data"]

    lo = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert lo.status_code == 200, lo.text
    lo_body = lo.json()
    assert set(lo_body.keys()) == {"data"}
    assert "message" in lo_body["data"]


def test_register_sends_verification_email(
    client: TestClient, stub_identity: StubIdentityProvider
) -> None:
    """A successful registration triggers exactly one verification email for that address."""
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@ex.com",
            "password": "secret123",
            "full_name": "New User",
            "clan_action": "create",
            "clan_name": "Nguyen",
            "clan_slug": "nguyen-test",
        },
    )
    assert resp.status_code == 201
    # stub_identity is module-scoped and shared with the other registration tests in
    # this file, so assert on this address specifically rather than list equality.
    assert stub_identity.verification_emails.count("newuser@ex.com") == 1


def test_register_compensation_sends_no_email_and_deletes_auth_user(
    client: TestClient, stub_identity: StubIdentityProvider, founder: dict[str, Any]
) -> None:
    """If clan-membership assignment fails AFTER the Supabase user is created, the
    handler must compensate (delete the orphaned auth user) and must NOT send a
    verification email for that registrant.

    Trigger: register a *different* email reusing ``founder``'s already-claimed
    clan slug. Reusing the shared ``founder`` fixture (rather than performing a
    fresh clan-creating registration here) avoids adding another audit-log row to
    the session-scoped DB — this suite runs alongside other integration modules
    that assert on audit-log pagination, so gratuitous extra rows are avoided.

    The slug-uniqueness check (``get_clan_by_slug``) runs inside
    ``_assign_clan_membership`` — which is only reached after
    ``identity.create_user`` has already succeeded for the new email — so the
    resulting ``ConflictError("auth.clan_slug_taken")`` genuinely exercises the
    handler's compensation ``except`` block, not a pre-create validation path.
    """
    second_email = f"second-{uuid.uuid4().hex[:8]}@example.com"

    # Registration with a different email, same slug as `founder`'s clan:
    # create_user succeeds (the email is unique), but _assign_clan_membership then
    # finds the slug taken and raises — reached only *after* the auth user for
    # second_email already exists.
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": second_email,
            "password": "s3cret-pass",
            "full_name": "Slug Squatter",
            "clan_action": "create",
            "clan_name": "Duplicate Clan",
            "clan_slug": founder["clan_slug"],
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "auth.clan_slug_taken"

    # No verification email was ever sent for the failed/rolled-back registrant.
    assert stub_identity.verification_emails.count(second_email) == 0
    # And the orphaned auth user was compensated away (deleted), proving the
    # compensation branch actually ran rather than merely failing silently.
    assert second_email not in stub_identity._users


# ── Negative controls: envelope + status codes stay truthful ─────


def test_missing_token_is_401_with_envelope(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "missing_token"
    assert "message" in body["error"]


def test_garbage_token_is_401_invalid_token(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_token"


def test_wrong_password_is_401_invalid_credentials(
    client: TestClient, founder: dict[str, Any]
) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": founder["email"], "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "auth.invalid_credentials"


def test_duplicate_email_registration_is_409(client: TestClient, founder: dict[str, Any]) -> None:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": founder["email"],
            "password": "another-pass",
            "full_name": "Imposter",
            "clan_action": "create",
            "clan_name": "Other Clan",
            "clan_slug": f"other-clan-{uuid.uuid4().hex[:8]}",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "auth.email_already_exists"


class _UnverifiedIdentityProvider:
    """Minimal stub: only sign_in is exercised by the login route."""

    async def sign_in(self, *, email: str, password: str) -> AuthenticatedIdentity:
        raise IdentityEmailNotVerifiedError("Email not confirmed")


def test_login_unverified_email_returns_403(client: TestClient) -> None:
    """An unconfirmed email must surface as 403 email_not_verified, not 401."""
    from app.infrastructure.dependencies import get_identity_provider

    original_override = client.app.dependency_overrides.get(get_identity_provider)  # type: ignore[attr-defined]
    client.app.dependency_overrides[get_identity_provider] = (  # type: ignore[attr-defined]
        lambda: _UnverifiedIdentityProvider()
    )
    try:
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "unverified@example.com", "password": "secret123"},
        )
    finally:
        if original_override is not None:
            client.app.dependency_overrides[get_identity_provider] = original_override  # type: ignore[attr-defined]
        else:
            client.app.dependency_overrides.pop(get_identity_provider, None)  # type: ignore[attr-defined]

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "email_not_verified"


def test_expired_token_is_rejected(client: TestClient, rsa_keys: dict[str, Any]) -> None:
    """The real verifier must enforce expiry on an otherwise valid signature."""
    past = datetime.now(UTC) - timedelta(hours=2)
    claims = {
        "sub": str(uuid.uuid4()),
        "email": "expired@example.com",
        "aud": "authenticated",
        "iss": _issuer(),
        "iat": past,
        "exp": past + timedelta(hours=1),
    }
    token = jwt.encode(claims, rsa_keys["private_pem"], algorithm="RS256", headers={"kid": _KID})
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_token"
