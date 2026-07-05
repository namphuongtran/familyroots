"""L12: the Invitation aggregate owns its lifecycle invariants + events.

These test the domain object in isolation. Concurrency (the accept-vs-revoke CAS)
lives in the handler + repository and is covered by the handler/integration tests;
here the in-memory status checks and event emission are what's under test.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.domain.invitation.entity import Invitation
from app.domain.invitation.events import (
    InvitationAccepted,
    InvitationCreated,
    InvitationRevoked,
)
from app.domain.shared.exceptions import ConflictError, ForbiddenError
from app.domain.shared.value_objects import ActorInfo

pytestmark = [pytest.mark.unit]


def _actor() -> ActorInfo:
    return ActorInfo(user_id=uuid.uuid4(), role="admin")


def _pending(**over: Any) -> Invitation:
    base: dict[str, Any] = {
        "clan_id": uuid.uuid4(),
        "email": "invited@x.com",
        "role": "editor",
        "token": "tok",
        "invited_by": uuid.uuid4(),
        "expires_at": datetime.now(UTC) + timedelta(days=1),
        "status": "pending",
    }
    base.update(over)
    return Invitation(**base)


def test_create_factory_emits_created_event() -> None:
    actor = _actor()
    exp = datetime.now(UTC) + timedelta(days=7)
    inv = Invitation.create(
        clan_id=uuid.uuid4(),
        email="a@x.com",
        role="viewer",
        invited_by=actor.user_id,
        token="tok-abc",
        expires_at=exp,
        actor=actor,
    )
    assert inv.status == "pending"
    events = inv.collect_events()
    assert len(events) == 1
    assert isinstance(events[0], InvitationCreated)
    assert events[0].resource_id == inv.id
    assert events[0].email == "a@x.com"
    assert events[0].invited_role == "viewer"


def test_accept_valid_sets_state_and_emits() -> None:
    inv = _pending(email="Invited@x.com")
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    inv.accept(user_id=user_id, user_email="invited@x.com", now=now)  # case-insensitive match

    assert inv.status == "accepted"
    assert inv.accepted_by == user_id
    assert inv.accepted_at == now
    events = inv.collect_events()
    assert len(events) == 1
    assert isinstance(events[0], InvitationAccepted)
    assert events[0].resource_id == inv.id


def test_accept_rejects_email_mismatch() -> None:
    inv = _pending(email="invited@x.com")
    with pytest.raises(ForbiddenError, match="email_mismatch"):
        inv.accept(user_id=uuid.uuid4(), user_email="other@x.com", now=datetime.now(UTC))
    assert inv.status == "pending"  # unchanged
    assert inv.collect_events() == []


def test_accept_rejects_expired() -> None:
    inv = _pending(expires_at=datetime.now(UTC) - timedelta(days=1))
    with pytest.raises(ConflictError, match="expired"):
        inv.accept(user_id=uuid.uuid4(), user_email="invited@x.com", now=datetime.now(UTC))
    assert inv.collect_events() == []


def test_accept_rejects_non_pending() -> None:
    inv = _pending(status="accepted")
    with pytest.raises(ConflictError, match="not_pending"):
        inv.accept(user_id=uuid.uuid4(), user_email="invited@x.com", now=datetime.now(UTC))


def test_revoke_pending_sets_revoked_and_emits() -> None:
    inv = _pending()
    inv.revoke(_actor())
    assert inv.status == "revoked"
    events = inv.collect_events()
    assert len(events) == 1
    assert isinstance(events[0], InvitationRevoked)
    assert events[0].resource_id == inv.id


def test_revoke_rejects_non_pending() -> None:
    inv = _pending(status="accepted")
    with pytest.raises(ConflictError, match="not_pending"):
        inv.revoke(_actor())
    assert inv.collect_events() == []
