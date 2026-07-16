"""Every blocking Supabase SDK call must run off the event loop.

The supabase-py SDK is synchronous: called directly inside an async def it
blocks the entire event loop for a full auth round-trip (~100-600 ms), so one
login stalls every in-flight request. These tests pin that each provider
method executes its SDK call in a worker thread (asyncio.to_thread), the same
way send_password_reset / send_verification_email already do.

Detection: inside a worker thread `asyncio.get_running_loop()` raises
RuntimeError; on the event-loop thread it succeeds.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

import app.infrastructure.supabase_identity_provider as mod

pytestmark = pytest.mark.asyncio


def _spy(ret: Any = None) -> tuple[Any, dict[str, bool]]:
    """A stand-in SDK function recording whether it ran on the event loop."""
    seen: dict[str, bool] = {}

    def fn(*args: Any, **kwargs: Any) -> Any:
        try:
            asyncio.get_running_loop()
            seen["on_loop"] = True
        except RuntimeError:
            seen["on_loop"] = False
        return ret

    return fn, seen


def _session() -> SimpleNamespace:
    return SimpleNamespace(access_token="at", refresh_token="rt", expires_in=3600)


async def test_create_user_offloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    fn, seen = _spy(SimpleNamespace(user=SimpleNamespace(id="uid-1")))
    client.auth.admin.create_user = fn
    monkeypatch.setattr(mod, "get_service_client", lambda: client)
    await mod.SupabaseIdentityProvider().create_user(email="a@example.com", password="pw")
    assert seen["on_loop"] is False


async def test_delete_user_offloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    fn, seen = _spy()
    client.auth.admin.delete_user = fn
    monkeypatch.setattr(mod, "get_service_client", lambda: client)
    await mod.SupabaseIdentityProvider().delete_user("uid-1")
    assert seen["on_loop"] is False


async def test_sign_in_offloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    fn, seen = _spy(
        SimpleNamespace(session=_session(), user=SimpleNamespace(id="uid-1", user_metadata={}))
    )
    client.auth.sign_in_with_password = fn
    monkeypatch.setattr(mod, "get_anon_client", lambda: client)
    await mod.SupabaseIdentityProvider().sign_in(email="a@example.com", password="pw")
    assert seen["on_loop"] is False


async def test_refresh_offloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    fn, seen = _spy(SimpleNamespace(session=_session()))
    client.auth.refresh_session = fn
    monkeypatch.setattr(mod, "get_anon_client", lambda: client)
    await mod.SupabaseIdentityProvider().refresh(refresh_token="rt")
    assert seen["on_loop"] is False


async def test_sign_out_offloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    fn, seen = _spy()
    client.auth.admin.sign_out = fn
    monkeypatch.setattr(mod, "get_service_client", lambda: client)
    await mod.SupabaseIdentityProvider().sign_out(access_token="at")
    assert seen["on_loop"] is False


async def test_update_user_offloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    fn, seen = _spy()
    client.auth.admin.update_user_by_id = fn
    monkeypatch.setattr(mod, "get_service_client", lambda: client)
    await mod.SupabaseIdentityProvider().update_user(
        user_id="uid-1", full_name="Tên Mới", preferred_locale=None
    )
    assert seen["on_loop"] is False
