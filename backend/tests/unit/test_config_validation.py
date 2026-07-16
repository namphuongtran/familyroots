"""Production config must fail fast on insecure values."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _build(**overrides):
    # _env_file=None so the developer's local .env does not interfere.
    return Settings(_env_file=None, **overrides)


def test_dev_defaults_ok():
    s = _build(APP_ENV="development")
    assert s.APP_DEBUG is False  # new default


def test_production_rejects_default_secret():
    with pytest.raises(ValidationError):
        _build(APP_ENV="production", APP_SECRET_KEY="change-me-in-production")


def test_production_rejects_debug_true():
    with pytest.raises(ValidationError):
        _build(APP_ENV="production", APP_SECRET_KEY="a-real-secret", APP_DEBUG=True)


def test_production_rejects_wildcard_allowed_hosts():
    with pytest.raises(ValidationError):
        _build(APP_ENV="production", APP_SECRET_KEY="a-real-secret", APP_DEBUG=False)


_PROD_SAFE = {
    "APP_ENV": "production",
    "APP_SECRET_KEY": "a-real-secret",
    "APP_DEBUG": False,
    "ALLOWED_HOSTS": ["example.com"],
    "DATABASE_URL": "postgresql+psycopg://u:p@db.prod.internal:5432/familyroots",
    "CORS_ORIGINS": ["https://app.example.com"],
    # Auth config is required in production (fail fast instead of per-request 503s).
    "SUPABASE_URL": "https://proj.supabase.co",
    "SUPABASE_ANON_KEY": "sb_publishable_x",
    "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_x",
    # Production must decide XFF trust explicitly; Render (proxied) → true.
    "RATE_LIMIT_TRUST_FORWARDED_FOR": True,
}


def test_production_with_safe_values_ok():
    s = _build(**_PROD_SAFE)
    assert s.APP_ENV == "production"


def test_production_rejects_localhost_database_url():
    with pytest.raises(ValidationError):
        _build(**{**_PROD_SAFE, "DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/x"})


def test_production_rejects_localhost_cors_origin():
    with pytest.raises(ValidationError):
        _build(**{**_PROD_SAFE, "CORS_ORIGINS": ["http://localhost:3000"]})


def test_production_requires_explicit_forwarded_for_decision():
    # Deployed behind a proxy (Render) with trust left unset, every client shares
    # the proxy's rate bucket and audit IPs record the proxy — production must
    # make the XFF-trust decision explicitly, either way.
    prod = {k: v for k, v in _PROD_SAFE.items() if k != "RATE_LIMIT_TRUST_FORWARDED_FOR"}
    with pytest.raises(ValidationError):
        _build(**prod)


def test_production_accepts_explicit_forwarded_for_true():
    s = _build(**{**_PROD_SAFE, "RATE_LIMIT_TRUST_FORWARDED_FOR": True})
    assert s.trust_forwarded_for is True


def test_production_accepts_explicit_forwarded_for_false():
    # Direct exposure (no proxy) is a legitimate deployment — trusting XFF there
    # would let clients spoof it — so an explicit False must also pass.
    s = _build(**{**_PROD_SAFE, "RATE_LIMIT_TRUST_FORWARDED_FOR": False})
    assert s.trust_forwarded_for is False


def test_dev_unset_forwarded_for_resolves_false():
    s = _build(APP_ENV="development")
    assert s.trust_forwarded_for is False
