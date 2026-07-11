"""send_password_reset off-loads the SDK call and passes redirect_to only when set."""

from unittest.mock import MagicMock

import pytest

import app.infrastructure.supabase_identity_provider as mod
from app.core.config import settings


@pytest.mark.asyncio
async def test_passes_redirect_to_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    monkeypatch.setattr(mod, "get_anon_client", lambda: client)
    # `settings` is a module-level singleton shared by both this test and the adapter
    # module (which does `from app.core.config import settings`), so patching it here
    # patches the same object the adapter reads.
    monkeypatch.setattr(settings, "PASSWORD_RESET_REDIRECT_URL", "https://app.example/reset")
    await mod.SupabaseIdentityProvider().send_password_reset(email="a@example.com")
    client.auth.reset_password_email.assert_called_once_with(
        "a@example.com", {"redirect_to": "https://app.example/reset"}
    )


@pytest.mark.asyncio
async def test_omits_redirect_to_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    monkeypatch.setattr(mod, "get_anon_client", lambda: client)
    monkeypatch.setattr(settings, "PASSWORD_RESET_REDIRECT_URL", "")
    await mod.SupabaseIdentityProvider().send_password_reset(email="a@example.com")
    client.auth.reset_password_email.assert_called_once_with("a@example.com", {})
