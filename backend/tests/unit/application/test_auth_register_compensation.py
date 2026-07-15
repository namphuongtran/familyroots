"""register() must delete the orphaned provider user if the DB membership fails."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.auth.handlers import AuthCommandHandler


@pytest.mark.asyncio
async def test_register_deletes_provider_user_on_db_failure(monkeypatch):
    new_id = uuid.uuid4()
    identity = AsyncMock()
    identity.create_user.return_value = str(new_id)

    # register() now validates clan input (incl. the slug-taken check) up front,
    # before create_user — so the repo double must answer get_clan_by_slug like a
    # real async repository (slug not taken) rather than the plain MagicMock this
    # test previously used, which isn't awaitable.
    repo = AsyncMock()
    repo.get_clan_by_slug.return_value = None

    handler = AuthCommandHandler(
        repo=repo, uow=MagicMock(), identity=identity, query_port=MagicMock()
    )

    async def _boom(**kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(handler, "_assign_clan_membership", _boom)

    with pytest.raises(RuntimeError, match="db exploded"):
        await handler.register(
            email="x@example.com",
            password="pw",
            full_name="X",
            clan_action="create",
            clan_name="C",
            clan_slug="c-slug",
        )

    # Compensation: the orphaned auth user was deleted via the port.
    identity.delete_user.assert_awaited_once_with(str(new_id))
