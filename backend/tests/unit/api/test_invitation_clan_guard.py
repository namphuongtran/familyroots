"""Path-clan guard tests for the three admin invitation routes.

Each admin route (create_invitation, list_invitations, revoke_invitation) must
raise HTTPException(403) when the path clan_id differs from the caller's
active_clan_id — BEFORE delegating to the handler.
"""

import types
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1 import invitations
from app.schemas.invitation import InvitationCreateRequest


class _FakeCommandHandler:
    async def create(self, *a, **k):
        raise AssertionError("handler must not be called on clan mismatch")

    async def revoke(self, *a, **k):
        raise AssertionError("handler must not be called on clan mismatch")


class _FakeQueryHandler:
    async def list_for_clan(self, *a, **k):
        raise AssertionError("handler must not be called on clan mismatch")


@pytest.mark.asyncio
async def test_create_invitation_rejects_path_clan_mismatch():
    path_clan = uuid.uuid4()
    active_clan = uuid.uuid4()  # different → guard must fire
    user = types.SimpleNamespace(id=uuid.uuid4())
    body = InvitationCreateRequest(email="a@x.com", role="viewer")

    with pytest.raises(HTTPException) as exc:
        await invitations.create_invitation(
            clan_id=path_clan,
            body=body,
            user=user,
            active_clan_id=active_clan,
            handler=_FakeCommandHandler(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_invitations_rejects_path_clan_mismatch():
    path_clan = uuid.uuid4()
    active_clan = uuid.uuid4()

    with pytest.raises(HTTPException) as exc:
        await invitations.list_invitations(
            clan_id=path_clan,
            user=object(),
            active_clan_id=active_clan,
            handler=_FakeQueryHandler(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_revoke_invitation_rejects_path_clan_mismatch():
    path_clan = uuid.uuid4()
    active_clan = uuid.uuid4()
    user = types.SimpleNamespace(id=uuid.uuid4())

    with pytest.raises(HTTPException) as exc:
        await invitations.revoke_invitation(
            clan_id=path_clan,
            invitation_id=uuid.uuid4(),
            user=user,
            active_clan_id=active_clan,
            handler=_FakeCommandHandler(),
        )
    assert exc.value.status_code == 403
