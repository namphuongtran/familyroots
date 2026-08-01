"""Unit tests for InvitationCommandHandler with in-memory fakes."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.application.invitation.commands import (
    AcceptInvitation,
    CreateInvitation,
    RevokeInvitation,
)
from app.application.invitation.handlers import InvitationCommandHandler
from app.domain.invitation.entity import Invitation
from app.domain.invitation.events import InvitationAccepted
from app.domain.shared.exceptions import ConflictError, EntityNotFoundError, ForbiddenError
from app.domain.shared.value_objects import ActorInfo


def _inv(**kw: Any) -> Invitation:
    """A real Invitation aggregate (the handler calls its accept()/revoke())."""
    return Invitation(**kw)


class _ExistingRole:
    def __init__(self):
        self.id = uuid.uuid4()
        self.role = "viewer"
        self.is_approved = False
        self.approved_by = None
        self.approved_at = None


class _FakeRepo:
    def __init__(
        self, pending=None, by_token=None, existing_role=None, by_id=None, transition_result=True
    ):
        self._pending = pending
        self._by_token = by_token
        self._existing_role = existing_role
        self._by_id = by_id
        self._transition_result = transition_result
        self.added_invitations = []
        self.added_roles = []
        self.ensured = []
        self.transition_calls = []
        self.call_order = []

    async def get_pending_by_email(self, clan_id, email):
        return self._pending

    async def expire_stale_pending(self, clan_id, email):
        self.call_order.append("expire_stale_pending")
        return 0

    async def get_by_token(self, token):
        return self._by_token

    async def get_by_id(self, invitation_id, clan_id):
        return self._by_id

    async def create_invitation(
        self, *, invitation_id, clan_id, email, role, invited_by, token, expires_at
    ):
        self.added_invitations.append(invitation_id)

    async def ensure_profile(self, user_id, email, display_name):
        self.call_order.append("ensure_profile")
        self.ensured.append(user_id)

    async def get_user_role(self, user_id, clan_id):
        return self._existing_role

    def add_membership(self, *, clan_id, user_id, role, approved_by, approved_at):
        self.call_order.append("add_membership")
        self.added_roles.append(
            SimpleNamespace(
                clan_id=clan_id,
                user_id=user_id,
                role=role,
                approved_by=approved_by,
                approved_at=approved_at,
                is_approved=True,
            )
        )

    async def promote_if_pending(self, ucr_id, *, role, approved_by, approved_at):
        # Mirror the real repo's atomic conditional UPDATE: promote a still-pending
        # row in place and report the win, so the fake stays consistent with the DB.
        self.call_order.append("promote_if_pending")
        r = self._existing_role
        if r is not None and getattr(r, "id", None) == ucr_id and not r.is_approved:
            r.role = role
            r.is_approved = True
            r.approved_by = approved_by
            r.approved_at = approved_at
            return True
        return False

    async def membership_is_approved(self, ucr_id):
        r = self._existing_role
        if r is None or getattr(r, "id", None) != ucr_id:
            return None
        return r.is_approved

    async def transition_status(
        self, invitation_id, *, expected, to, accepted_by=None, accepted_at=None
    ):
        self.call_order.append("transition_status")
        self.transition_calls.append(
            {
                "invitation_id": invitation_id,
                "expected": expected,
                "to": to,
                "accepted_by": accepted_by,
                "accepted_at": accepted_at,
            }
        )
        if self._transition_result:
            # Mirror the real repo's atomic write so the in-memory fake stays
            # consistent with the DB-backed implementation.
            if self._by_token is not None and self._by_token.id == invitation_id:
                self._by_token.status = to
            if self._by_id is not None and self._by_id.id == invitation_id:
                self._by_id.status = to
        return self._transition_result


class _FakeUow:
    def __init__(self):
        self.commits = 0
        self.tracked: list[Any] = []

    def track(self, agg):
        self.tracked.append(agg)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1


def _actor():
    return ActorInfo(user_id=uuid.uuid4(), role="admin")


@pytest.mark.asyncio
async def test_create_rejects_duplicate_pending():
    repo = _FakeRepo(pending=_inv())
    handler = InvitationCommandHandler(repo, _FakeUow())  # type: ignore[arg-type]
    with pytest.raises(ConflictError):
        await handler.create(
            CreateInvitation(clan_id=uuid.uuid4(), email="a@x.com", role="viewer", actor=_actor())
        )


@pytest.mark.asyncio
async def test_create_returns_token_and_path():
    repo = _FakeRepo()
    handler = InvitationCommandHandler(repo, _FakeUow())  # type: ignore[arg-type]
    out = await handler.create(
        CreateInvitation(clan_id=uuid.uuid4(), email="A@X.com", role="editor", actor=_actor())
    )
    assert out["token"]
    assert len(out["token"]) >= 32
    assert out["accept_path"] == f"/api/v1/invitations/{out['token']}/accept"
    assert out["email"] == "a@x.com"  # normalized
    assert len(repo.added_invitations) == 1


@pytest.mark.asyncio
async def test_accept_email_mismatch_forbidden():
    inv = _inv(
        clan_id=uuid.uuid4(),
        email="invited@x.com",
        role="viewer",
        invited_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    repo = _FakeRepo(by_token=inv)
    handler = InvitationCommandHandler(repo, _FakeUow())  # type: ignore[arg-type]
    with pytest.raises(ForbiddenError):
        await handler.accept(
            AcceptInvitation(
                token="t", user_id=uuid.uuid4(), user_email="someone-else@x.com", user_full_name="X"
            )
        )


@pytest.mark.asyncio
async def test_accept_expired_conflict():
    inv = _inv(
        clan_id=uuid.uuid4(),
        email="a@x.com",
        role="viewer",
        invited_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    repo = _FakeRepo(by_token=inv)
    handler = InvitationCommandHandler(repo, _FakeUow())  # type: ignore[arg-type]
    with pytest.raises(ConflictError):
        await handler.accept(
            AcceptInvitation(
                token="t", user_id=uuid.uuid4(), user_email="a@x.com", user_full_name="X"
            )
        )


@pytest.mark.asyncio
async def test_accept_creates_approved_membership():
    inv = _inv(
        clan_id=uuid.uuid4(),
        email="a@x.com",
        role="editor",
        invited_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    repo = _FakeRepo(by_token=inv)
    uow = _FakeUow()
    handler = InvitationCommandHandler(repo, uow)  # type: ignore[arg-type]
    out = await handler.accept(
        AcceptInvitation(token="t", user_id=uuid.uuid4(), user_email="A@x.com", user_full_name="X")
    )
    assert out["role"] == "editor"
    assert inv.status == "accepted"
    assert len(repo.added_roles) == 1
    role = repo.added_roles[0]
    assert role.is_approved is True
    assert role.approved_by == inv.invited_by and role.approved_at is not None
    assert uow.commits == 1
    # claim won → aggregate tracked so its InvitationAccepted event is dispatched
    assert uow.tracked == [inv]


@pytest.mark.asyncio
async def test_accept_promotes_pending_membership():
    inv = _inv(
        clan_id=uuid.uuid4(),
        email="a@x.com",
        role="editor",
        invited_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    existing = _ExistingRole()
    repo = _FakeRepo(by_token=inv, existing_role=existing)
    uow = _FakeUow()
    handler = InvitationCommandHandler(repo, uow)  # type: ignore[arg-type]

    out = await handler.accept(
        AcceptInvitation(token="t", user_id=uuid.uuid4(), user_email="a@x.com", user_full_name="X")
    )

    assert out["role"] == "editor"
    # Promoted in place — no NEW role row added:
    assert repo.added_roles == []
    assert existing.role == "editor"
    assert existing.is_approved is True
    assert existing.approved_by == inv.invited_by
    assert existing.approved_at is not None
    assert inv.status == "accepted"


@pytest.mark.asyncio
async def test_revoke_pending_sets_revoked():
    inv = _inv(status="pending")
    repo = _FakeRepo(by_id=inv)
    uow = _FakeUow()
    handler = InvitationCommandHandler(repo, uow)  # type: ignore[arg-type]
    await handler.revoke(
        RevokeInvitation(clan_id=uuid.uuid4(), invitation_id=inv.id, actor=_actor())
    )
    assert inv.status == "revoked"
    assert uow.commits == 1


@pytest.mark.asyncio
async def test_revoke_nonpending_conflicts():
    inv = _inv(status="accepted")
    repo = _FakeRepo(by_id=inv)
    handler = InvitationCommandHandler(repo, _FakeUow())  # type: ignore[arg-type]
    with pytest.raises(ConflictError):
        await handler.revoke(
            RevokeInvitation(clan_id=uuid.uuid4(), invitation_id=inv.id, actor=_actor())
        )


@pytest.mark.asyncio
async def test_revoke_not_found():
    repo = _FakeRepo(by_id=None)
    handler = InvitationCommandHandler(repo, _FakeUow())  # type: ignore[arg-type]
    with pytest.raises(EntityNotFoundError):
        await handler.revoke(
            RevokeInvitation(clan_id=uuid.uuid4(), invitation_id=uuid.uuid4(), actor=_actor())
        )


@pytest.mark.asyncio
async def test_accept_conflicts_when_transition_loses_race():
    """A concurrent revoke wins the row: transition_status returns False,
    so accept must 409 and never grant a role."""
    inv = _inv(
        clan_id=uuid.uuid4(),
        email="a@x.com",
        role="editor",
        invited_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    repo = _FakeRepo(by_token=inv, transition_result=False)
    uow = _FakeUow()
    handler = InvitationCommandHandler(repo, uow)  # type: ignore[arg-type]
    with pytest.raises(ConflictError, match=r"invitation\.not_pending"):
        await handler.accept(
            AcceptInvitation(
                token="t", user_id=uuid.uuid4(), user_email="a@x.com", user_full_name="X"
            )
        )
    assert repo.added_roles == []
    # The aggregate buffered an InvitationAccepted event in accept(), but the lost CAS
    # means it is never tracked — so the event is discarded, never dispatched/committed.
    assert uow.tracked == []
    assert uow.commits == 0
    assert any(isinstance(e, InvitationAccepted) for e in inv.collect_events())


@pytest.mark.asyncio
async def test_revoke_conflicts_when_transition_loses_race():
    """A concurrent accept wins the row: transition_status returns False,
    so revoke must 409."""
    inv = _inv(status="pending")
    repo = _FakeRepo(by_id=inv, transition_result=False)
    handler = InvitationCommandHandler(repo, _FakeUow())  # type: ignore[arg-type]
    with pytest.raises(ConflictError, match=r"invitation\.not_pending"):
        await handler.revoke(
            RevokeInvitation(clan_id=uuid.uuid4(), invitation_id=inv.id, actor=_actor())
        )


@pytest.mark.asyncio
async def test_accept_claims_before_granting_role():
    """transition_status must be called before add_membership, so a lost
    race can never leave a granted role behind."""
    inv = _inv(
        clan_id=uuid.uuid4(),
        email="a@x.com",
        role="editor",
        invited_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    repo = _FakeRepo(by_token=inv)
    handler = InvitationCommandHandler(repo, _FakeUow())  # type: ignore[arg-type]
    await handler.accept(
        AcceptInvitation(token="t", user_id=uuid.uuid4(), user_email="a@x.com", user_full_name="X")
    )
    assert repo.call_order.index("transition_status") < repo.call_order.index("add_membership")
