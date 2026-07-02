"""IdentityUnavailableError must surface as a 503 in the standard envelope,
and production settings must fail fast when auth config is missing."""

import json
from typing import Any

import pytest
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.core.config import Settings
from app.core.exceptions import identity_unavailable_handler
from app.domain.auth.identity_provider import IdentityUnavailableError

pytestmark = [pytest.mark.unit]

_REQ = Request({"type": "http", "method": "POST", "path": "/api/v1/auth/login", "headers": []})


def _body(response: JSONResponse) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(bytes(response.body))
    return parsed


@pytest.mark.asyncio
async def test_identity_unavailable_returns_503_envelope() -> None:
    resp = await identity_unavailable_handler(_REQ, IdentityUnavailableError("dns fail"))
    assert resp.status_code == 503
    body = _body(resp)
    assert body["error"]["code"] == "auth_provider_unavailable"
    assert set(body["error"]) == {"code", "message", "detail"}


_PROD_BASE: dict[str, Any] = {
    "APP_ENV": "production",
    "APP_SECRET_KEY": "real-secret",
    "APP_DEBUG": False,
    "ALLOWED_HOSTS": ["api.example.com"],
    "DATABASE_URL": "postgresql+psycopg://u:p@db.example.com:5432/x",
    "CORS_ORIGINS": ["https://app.example.com"],
    "SUPABASE_URL": "https://proj.supabase.co",
    "SUPABASE_ANON_KEY": "sb_publishable_x",
    "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_x",
}


def test_production_settings_accept_complete_auth_config() -> None:
    assert Settings(**_PROD_BASE).SUPABASE_URL


@pytest.mark.parametrize(
    "missing", ["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"]
)
def test_production_settings_require_auth_config(missing: str) -> None:
    cfg = {**_PROD_BASE, missing: ""}
    with pytest.raises(ValueError, match=missing):
        Settings(**cfg)
