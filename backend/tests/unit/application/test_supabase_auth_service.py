"""AuthSessionService.logout must revoke the session via the IdentityProvider port."""

from unittest.mock import AsyncMock

import pytest

from app.application.auth.handlers import AuthSessionService


@pytest.mark.asyncio
async def test_logout_revokes_session():
    identity = AsyncMock()
    svc = AuthSessionService(identity)

    await svc.logout(access_token="the-access-token")

    # The service delegates revocation to the identity provider.
    identity.sign_out.assert_awaited_once_with(access_token="the-access-token")
