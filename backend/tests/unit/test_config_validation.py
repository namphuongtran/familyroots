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


def test_production_with_safe_values_ok():
    s = _build(APP_ENV="production", APP_SECRET_KEY="a-real-secret", APP_DEBUG=False)
    assert s.APP_ENV == "production"
