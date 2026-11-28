"""#297: a sign-up that reuses a deleted account's email must not 500.

Seed a profile (id A, email X), then authenticate as a different ``sub`` B with
the same email over HTTP with a real RS256 JWT, and read the status and body.
The old profile is never re-linked to B: that would hand A's clan roles to a
new sign-up. On ``main`` this request answers 500 (IntegrityError on
``uq_user_profiles_email``).
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

_KID = "email-reuse-key"


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
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
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


def _mint(private_pem: str, user_id: uuid.UUID, email: str) -> str:
    now = datetime.now(UTC)
    issuer = f"{security_module.settings.SUPABASE_URL.rstrip('/')}/auth/v1"  # type: ignore[attr-defined]
    claims = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "iss": issuer,
        "iat": now,
        "exp": now + timedelta(hours=1),
        "user_metadata": {"full_name": "Reused Email"},
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
    app.dependency_overrides[get_system_db] = _override_db
    # raise_server_exceptions=False: a 500 must read as a 500, not as a raised error.
    yield TestClient(app, raise_server_exceptions=False)
    engine.sync_engine.dispose()


def _seed_old_profile(dsn: str) -> tuple[uuid.UUID, str]:
    old_id = uuid.uuid4()
    email = f"reuse-{old_id.hex[:8]}@ex.com"
    eng = sa.create_engine(dsn.replace("+asyncpg", ""))
    try:
        with eng.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name) VALUES (:u, :e, 'Old')"
                ),
                {"u": old_id, "e": email},
            )
    finally:
        eng.dispose()
    return old_id, email


def _profile_ids_for(dsn: str, email: str) -> list[uuid.UUID]:
    eng = sa.create_engine(dsn.replace("+asyncpg", ""))
    try:
        with eng.connect() as conn:
            rows = conn.execute(
                sa.text("SELECT id FROM user_profiles WHERE email = :e"), {"e": email}
            ).all()
        return [r[0] for r in rows]
    finally:
        eng.dispose()


def test_new_sub_with_an_existing_profiles_email_is_refused_not_500(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    old_id, email = _seed_old_profile(migrated_db_url)
    new_id = uuid.uuid4()
    token = _mint(rsa_keys["private_pem"], new_id, email)

    resp = client.get("/api/v1/claims", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "email_already_registered"
    # Nothing re-linked, nothing created: the old profile keeps its id.
    assert _profile_ids_for(migrated_db_url, email) == [old_id]


def test_same_sub_with_its_own_profile_still_succeeds(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    """Positive control: the owner of the profile is not refused."""
    old_id, email = _seed_old_profile(migrated_db_url)
    token = _mint(rsa_keys["private_pem"], old_id, email)

    resp = client.get("/api/v1/claims", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200, resp.text
