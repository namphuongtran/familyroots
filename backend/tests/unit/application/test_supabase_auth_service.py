"""SupabaseAuthService.logout must revoke the user's session via Supabase."""

from unittest.mock import MagicMock

import pytest

from app.application.auth import handlers


@pytest.mark.asyncio
async def test_logout_revokes_session(monkeypatch):
    admin = MagicMock()
    monkeypatch.setattr(handlers, "_supabase_admin", lambda: admin)

    svc = handlers.SupabaseAuthService()
    await svc.logout(access_token="the-access-token")

    # The service must have asked Supabase to sign the session out.
    assert admin.auth.admin.sign_out.called
