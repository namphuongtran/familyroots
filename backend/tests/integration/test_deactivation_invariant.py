"""H1 (review 2026-07-18): deactivation must be an invariant, not a per-route accident.

Drives the previously-BYPASSED routes over HTTP with REAL RS256 JWTs (the JWKS
cache is primed with a test keypair so ``verify_supabase_token`` runs for real)
and a real migrated DB. ``get_current_user`` is NOT dependency-overridden — that
is the point: these tests exercise the chokepoint gate itself. A revert of the
gate in ``get_current_user`` fails every 403 assertion here.

Rate-limit budget: this module's app instance shares the 20 req/min/IP bucket on
/api/v1/auth + /api/v1/invitations — keep total requests on those prefixes low.
"""

import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwk, jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.security as security_module
from app.core.database import get_db, get_system_db
from app.main import create_app

pytestmark = pytest.mark.integration

_KID = "deact-test-key"


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
    old_cache, old_time = security_module._jwks_cache, security_module._jwks_cache_time
    security_module._jwks_cache = rsa_keys["jwks"]
    security_module._jwks_cache_time = time.monotonic()
    yield
    security_module._jwks_cache, security_module._jwks_cache_time = old_cache, old_time


def _issuer() -> str:
    return f"{security_module.settings.SUPABASE_URL.rstrip('/')}/auth/v1"  # type: ignore[attr-defined]


def _mint(private_pem: str, user_id: uuid.UUID, email: str) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "iss": _issuer(),
        "iat": now,
        "exp": now + timedelta(hours=1),
        "user_metadata": {"full_name": "Deact Test"},
    }
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": _KID})


@pytest.fixture(scope="module")
def client(migrated_db_url: str, jwks_cache: None) -> Iterator[TestClient]:
    app = create_app()
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    # ADR-048: POST /invitations/{token}/accept runs on the privileged system session
    # (it has no clan context), so the test session must be injected there too.
    app.dependency_overrides[get_system_db] = _override_db
    yield TestClient(app)
    engine.sync_engine.dispose()


def _sync_engine(dsn: str) -> sa.Engine:
    return sa.create_engine(dsn.replace("+asyncpg", ""))


def _seed_profile(dsn: str, *, active: bool) -> tuple[uuid.UUID, str]:
    """Insert a user_profiles row; return (user_id, email)."""
    user_id = uuid.uuid4()
    email = f"deact-{user_id.hex[:8]}@ex.com"
    eng = _sync_engine(dsn)
    try:
        with eng.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name, is_active) "
                    "VALUES (:u, :e, 'U', :act)"
                ),
                {"u": user_id, "e": email, "act": active},
            )
    finally:
        eng.dispose()
    return user_id, email


def _seed_invitation(dsn: str, *, email: str) -> tuple[str, uuid.UUID]:
    """Clan + admin inviter + pending invitation for `email`; return (token, clan_id)."""
    clan_id, inviter_id = uuid.uuid4(), uuid.uuid4()
    token = f"tok-{uuid.uuid4().hex}"
    eng = _sync_engine(dsn)
    try:
        with eng.begin() as conn:
            conn.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:c, 'C', :sl)"),
                {"c": clan_id, "sl": f"c-{clan_id.hex[:8]}"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name) VALUES (:u, :e, 'Inviter')"
                ),
                {"u": inviter_id, "e": f"inv-{inviter_id.hex[:8]}@ex.com"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO user_clan_roles (user_id, clan_id, role, is_approved, "
                    "approved_by, approved_at) VALUES (:u, :c, 'admin', true, :u, now())"
                ),
                {"u": inviter_id, "c": clan_id},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO clan_invitations (id, clan_id, email, role, status, "
                    "invited_by, token, expires_at) VALUES (:i, :c, :e, 'viewer', "
                    "'pending', :inv, :t, now() + interval '7 days')"
                ),
                {"i": uuid.uuid4(), "c": clan_id, "e": email, "inv": inviter_id, "t": token},
            )
    finally:
        eng.dispose()
    return token, clan_id


def _membership_exists(dsn: str, user_id: uuid.UUID, clan_id: uuid.UUID) -> bool:
    eng = _sync_engine(dsn)
    try:
        with eng.connect() as conn:
            row = conn.execute(
                sa.text("SELECT 1 FROM user_clan_roles WHERE user_id = :u AND clan_id = :c"),
                {"u": user_id, "c": clan_id},
            ).first()
        return row is not None
    finally:
        eng.dispose()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_deactivated(resp: Any) -> None:
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "account_deactivated"


def test_deactivated_403_on_auth_me(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    user_id, email = _seed_profile(migrated_db_url, active=False)
    resp = client.get(
        "/api/v1/auth/me", headers=_auth(_mint(rsa_keys["private_pem"], user_id, email))
    )
    _assert_deactivated(resp)


def test_deactivated_403_on_me_clans(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    user_id, email = _seed_profile(migrated_db_url, active=False)
    resp = client.get(
        "/api/v1/me/clans", headers=_auth(_mint(rsa_keys["private_pem"], user_id, email))
    )
    _assert_deactivated(resp)


def test_deactivated_403_on_onboard(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    user_id, email = _seed_profile(migrated_db_url, active=False)
    resp = client.post(
        "/api/v1/auth/onboard",
        headers=_auth(_mint(rsa_keys["private_pem"], user_id, email)),
        json={
            "clan_action": "create",
            "clan_name": "Deact Clan",
            "clan_slug": f"deact-{user_id.hex[:8]}",
        },
    )
    _assert_deactivated(resp)


def test_deactivated_cannot_accept_invitation(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    """The privilege escalation from the review: a deactivated user must not be
    able to convert a pending invitation into an approved membership."""
    user_id, email = _seed_profile(migrated_db_url, active=False)
    token, clan_id = _seed_invitation(migrated_db_url, email=email)
    resp = client.post(
        f"/api/v1/invitations/{token}/accept",
        headers=_auth(_mint(rsa_keys["private_pem"], user_id, email)),
    )
    _assert_deactivated(resp)
    assert not _membership_exists(migrated_db_url, user_id, clan_id)


def test_active_user_positive_control(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    """Same wiring, active profile → the gate must NOT fire."""
    user_id, email = _seed_profile(migrated_db_url, active=True)
    resp = client.get(
        "/api/v1/auth/me", headers=_auth(_mint(rsa_keys["private_pem"], user_id, email))
    )
    assert resp.status_code == 200, resp.text


def test_missing_profile_is_not_deactivated(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    """None != False: a brand-new account (no profile row yet) must pass the
    chokepoint so first-login provisioning keeps working."""
    user_id = uuid.uuid4()  # never seeded
    resp = client.get(
        "/api/v1/me/clans",
        headers=_auth(_mint(rsa_keys["private_pem"], user_id, f"new-{user_id.hex[:8]}@ex.com")),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []


# ── Login gate (handler-level; no JWT dependency runs on /auth/login) ──────────

from app.domain.auth.identity_provider import (  # noqa: E402
    AuthenticatedIdentity,
    AuthTokens,
    IdentityAuthError,
)
from app.infrastructure.dependencies import get_identity_provider  # noqa: E402


class _LoginStub:
    """sign_in-only identity stub — the login-gate tests need no other provider op."""

    def __init__(self, user_id: uuid.UUID, email: str, password: str) -> None:
        self._user_id, self._email, self._password = user_id, email, password

    async def sign_in(self, *, email: str, password: str) -> AuthenticatedIdentity:
        if email != self._email or password != self._password:
            raise IdentityAuthError("invalid credentials")
        return AuthenticatedIdentity(
            user_id=str(self._user_id),
            email=email,
            full_name="Deact Login",
            tokens=AuthTokens(
                access_token="stub-access", refresh_token="stub-refresh", expires_in=3600
            ),
        )


def _login(client: TestClient, stub: _LoginStub, email: str, password: str) -> Any:
    original = client.app.dependency_overrides.get(get_identity_provider)  # type: ignore[attr-defined]
    client.app.dependency_overrides[get_identity_provider] = lambda: stub  # type: ignore[attr-defined]
    try:
        return client.post("/api/v1/auth/login", json={"email": email, "password": password})
    finally:
        if original is not None:
            client.app.dependency_overrides[get_identity_provider] = original  # type: ignore[attr-defined]
        else:
            client.app.dependency_overrides.pop(get_identity_provider, None)  # type: ignore[attr-defined]


def test_deactivated_login_rejected_no_tokens(client: TestClient, migrated_db_url: str) -> None:
    """Valid credentials + deactivated profile → 403, and the body must contain
    neither tokens nor profile data."""
    user_id, email = _seed_profile(migrated_db_url, active=False)
    resp = _login(client, _LoginStub(user_id, email, "pw-1"), email, "pw-1")
    _assert_deactivated(resp)
    assert "access_token" not in resp.text
    assert "refresh_token" not in resp.text


def test_active_login_positive_control(client: TestClient, migrated_db_url: str) -> None:
    user_id, email = _seed_profile(migrated_db_url, active=True)
    resp = _login(client, _LoginStub(user_id, email, "pw-2"), email, "pw-2")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["access_token"] == "stub-access"
