"""JWKS fetch must be bounded and fail as a truthful 503.

On a cache miss (cold start or hourly TTL expiry) every request needing token
verification goes through get_supabase_jwks. Without a timeout a hung Supabase
JWKS endpoint stalls the whole service; without error mapping a transport
failure escapes as a raw httpx exception → opaque 500 instead of the 503
auth_provider_unavailable envelope the rest of the auth path uses.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

import httpx
import pytest

from app.core import security
from app.core.config import settings
from app.domain.auth.identity_provider import IdentityUnavailableError

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "_jwks_cache", None)
    monkeypatch.setattr(security, "_jwks_cache_time", 0.0)
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")


class _FailingClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> _FailingClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def get(self, url: str) -> Any:
        raise httpx.ConnectTimeout("connection timed out")


class _CapturingClient:
    kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _CapturingClient.kwargs = kwargs

    async def __aenter__(self) -> _CapturingClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def get(self, url: str) -> Any:
        class _Resp:
            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict[str, Any]:
                return {"keys": []}

        return _Resp()


class _NonJsonClient:
    """A 200 response whose body is not JSON — e.g. a captive portal / proxy / gateway
    returning an HTML error page. ``raise_for_status`` passes; ``json()`` blows up."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> _NonJsonClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def get(self, url: str) -> Any:
        class _Resp:
            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict[str, Any]:
                raise json.JSONDecodeError("Expecting value", "<html>503</html>", 0)

        return _Resp()


async def test_jwks_transport_failure_maps_to_identity_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _FailingClient)
    with pytest.raises(IdentityUnavailableError):
        await security.get_supabase_jwks()


async def test_jwks_non_json_body_maps_to_identity_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 200 with a non-JSON body (proxy/captive-portal error page) must be a truthful
    503, not a JSONDecodeError -> 500 on every token-verified request during the
    cache-miss window (resp.json() previously sat outside the httpx.HTTPError guard)."""
    monkeypatch.setattr(httpx, "AsyncClient", _NonJsonClient)
    with pytest.raises(IdentityUnavailableError):
        await security.get_supabase_jwks()


async def test_jwks_client_is_constructed_with_a_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _CapturingClient.kwargs = {}
    monkeypatch.setattr(httpx, "AsyncClient", _CapturingClient)
    await security.get_supabase_jwks()
    assert _CapturingClient.kwargs.get("timeout") is not None
