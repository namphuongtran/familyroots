"""verify_supabase_token must reject tokens with a wrong issuer."""

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk, jwt
from jose.constants import ALGORITHMS

from app.core import security
from app.core.config import settings


def _make_keypair_and_jwk():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    public_jwk = jwk.construct(pub_pem, ALGORITHMS.RS256).to_dict()
    public_jwk["kid"] = "test-key"
    public_jwk = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in public_jwk.items()}
    return priv_pem, {"keys": [public_jwk]}


@pytest.fixture()
def signing(monkeypatch):
    priv_pem, jwks = _make_keypair_and_jwk()
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")

    async def _fake_jwks():
        return jwks

    monkeypatch.setattr(security, "get_supabase_jwks", _fake_jwks)
    return priv_pem


def _token(priv_pem, iss):
    return jwt.encode(
        {"sub": "u1", "aud": "authenticated", "iss": iss, "exp": 9999999999},
        priv_pem,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


@pytest.mark.asyncio
async def test_correct_issuer_accepted(signing):
    token = _token(signing, "https://proj.supabase.co/auth/v1")
    payload = await security.verify_supabase_token(token)
    assert payload["sub"] == "u1"


@pytest.mark.asyncio
async def test_wrong_issuer_rejected(signing):
    from fastapi import HTTPException

    token = _token(signing, "https://evil.example.com/auth/v1")
    with pytest.raises(HTTPException) as exc:
        await security.verify_supabase_token(token)
    assert exc.value.status_code == 401
