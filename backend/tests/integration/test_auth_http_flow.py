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
    yield TestClient(app)


# ── Happy path: the full flow that hid #12/#13 ────────────────────


def test_register_login_me_clans_create_person(client: TestClient) -> None:
    email, password = "smoke-founder@example.com", "s3cret-pass"

    # Register, creating a clan → approved admin membership.
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Smoke Founder",
            "clan_action": "create",
            "clan_name": "Smoke Clan",
            "clan_slug": "smoke-clan",
        },
    )
    assert resp.status_code == 201, resp.text
    reg = resp.json()
    assert reg["is_approved"] is True
    clan_id = reg["clan_id"]

    # Login — exercises the CQRS login-profile read model (the seam of #13).
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    login = resp.json()
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

    # /me/clans — membership projection.
    resp = client.get("/api/v1/me/clans", headers=auth)
    assert resp.status_code == 200, resp.text
    clans = resp.json()
    assert clans["count"] == 1
    assert clans["clans"][0]["clan_id"] == clan_id
    assert clans["clans"][0]["role"] == "admin"

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


def test_wrong_password_is_401_invalid_credentials(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "smoke-founder@example.com", "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "auth.invalid_credentials"


def test_duplicate_email_registration_is_409(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "smoke-founder@example.com",
            "password": "another-pass",
            "full_name": "Imposter",
            "clan_action": "create",
            "clan_name": "Other Clan",
            "clan_slug": "other-clan",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "auth.email_already_exists"


def test_expired_token_is_rejected(
    client: TestClient, rsa_keys: dict[str, Any], stub_identity: StubIdentityProvider
) -> None:
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
