"""register() must delete the orphaned Supabase user if the DB membership fails."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.application.auth import handlers
from app.application.auth.handlers import AuthCommandHandler


@pytest.mark.asyncio
async def test_register_deletes_supabase_user_on_db_failure(monkeypatch):
    new_id = uuid.uuid4()
    admin = MagicMock()
    admin.auth.admin.create_user.return_value = MagicMock(user=MagicMock(id=str(new_id)))
    monkeypatch.setattr(handlers, "_supabase_admin", lambda: admin)

    handler = AuthCommandHandler(repo=MagicMock(), uow=MagicMock())

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

    # Compensation: the orphaned auth user was deleted.
    admin.auth.admin.delete_user.assert_called_once_with(str(new_id))
