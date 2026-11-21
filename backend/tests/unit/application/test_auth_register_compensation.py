"""register() must delete the orphaned provider user if the local profile write fails."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.auth.command_handler import AuthCommandHandler


@pytest.mark.asyncio
async def test_register_deletes_provider_user_on_db_failure(monkeypatch):
    new_id = uuid.uuid4()
    identity = AsyncMock()
    identity.create_user.return_value = str(new_id)

    repo = AsyncMock()

    handler = AuthCommandHandler(
        repo=repo, uow=MagicMock(), identity=identity, query_port=MagicMock()
    )

    async def _boom(**kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(handler, "_provision_clanless_account", _boom)

    with pytest.raises(RuntimeError, match="db exploded"):
        await handler.register(
            email="x@example.com",
            password="pw",
            full_name="X",
        )

    # Compensation: the orphaned auth user was deleted via the port.
    identity.delete_user.assert_awaited_once_with(str(new_id))
