"""Unit tests for InvitationCommandHandler with in-memory fakes."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.application.invitation.commands import (
    AcceptInvitation,
    CreateInvitation,
)
from app.application.invitation.handlers import InvitationCommandHandler
from app.domain.shared.exceptions import ConflictError, ForbiddenError
from app.domain.shared.value_objects import ActorInfo


class _Inv:
    def __init__(self, **kw):
        self.id = uuid.uuid4()
        self.status = "pending"
        self.accepted_by = None
        self.accepted_at = None
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeRepo:
    def __init__(self, pending=None, by_token=None, existing_role=None):
        self._pending = pending
        self._by_token = by_token
        self._existing_role = existing_role
        self.added_invitations = []
        self.added_roles = []
        self.ensured = []

    async def get_pending_by_email(self, clan_id, email):
        return self._pending

    async def get_by_token(self, token):
        return self._by_token

    def add_invitation(self, inv):
        self.added_invitations.append(inv)

    async def ensure_profile(self, user_id, email, display_name):
        self.ensured.append(user_id)

    async def get_user_role(self, user_id, clan_id):
        return self._existing_role

    def add_user_role(self, role):
        self.added_roles.append(role)


class _FakeUow:
    def __init__(self):
        self.commits = 0

    def track(self, agg):
        pass

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1


def _actor():
    return ActorInfo(user_id=uuid.uuid4(), role="admin")


@pytest.mark.asyncio
async def test_create_rejects_duplicate_pending():
    repo = _FakeRepo(pending=_Inv())
    handler = InvitationCommandHandler(repo, _FakeUow())
    with pytest.raises(ConflictError):
        await handler.create(
            CreateInvitation(clan_id=uuid.uuid4(), email="a@x.com", role="viewer", actor=_actor())
        )


@pytest.mark.asyncio
async def test_create_returns_token_and_path():
    repo = _FakeRepo()
    handler = InvitationCommandHandler(repo, _FakeUow())
    out = await handler.create(
        CreateInvitation(clan_id=uuid.uuid4(), email="A@X.com", role="editor", actor=_actor())
    )
    assert out["token"]
    assert out["accept_path"] == f"/api/v1/invitations/{out['token']}/accept"
    assert out["email"] == "a@x.com"  # normalized
    assert len(repo.added_invitations) == 1


@pytest.mark.asyncio
async def test_accept_email_mismatch_forbidden():
    inv = _Inv(
        clan_id=uuid.uuid4(), email="invited@x.com", role="viewer", invited_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    repo = _FakeRepo(by_token=inv)
    handler = InvitationCommandHandler(repo, _FakeUow())
    with pytest.raises(ForbiddenError):
        await handler.accept(
            AcceptInvitation(token="t", user_id=uuid.uuid4(),
                             user_email="someone-else@x.com", user_full_name="X")
        )


@pytest.mark.asyncio
async def test_accept_expired_conflict():
    inv = _Inv(
        clan_id=uuid.uuid4(), email="a@x.com", role="viewer", invited_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    repo = _FakeRepo(by_token=inv)
    handler = InvitationCommandHandler(repo, _FakeUow())
    with pytest.raises(ConflictError):
        await handler.accept(
            AcceptInvitation(token="t", user_id=uuid.uuid4(), user_email="a@x.com",
                             user_full_name="X")
        )


@pytest.mark.asyncio
async def test_accept_creates_approved_membership():
    inv = _Inv(
        clan_id=uuid.uuid4(), email="a@x.com", role="editor", invited_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    repo = _FakeRepo(by_token=inv)
    uow = _FakeUow()
    handler = InvitationCommandHandler(repo, uow)
    out = await handler.accept(
        AcceptInvitation(token="t", user_id=uuid.uuid4(), user_email="A@x.com",
                         user_full_name="X")
    )
    assert out["role"] == "editor"
    assert inv.status == "accepted"
    assert len(repo.added_roles) == 1
    role = repo.added_roles[0]
    assert role.is_approved is True
    assert role.approved_by == inv.invited_by and role.approved_at is not None
    assert uow.commits == 1
