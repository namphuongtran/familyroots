"""L12: the Invitation aggregate owns its lifecycle invariants + events.

These test the domain object in isolation. Concurrency (the accept-vs-revoke CAS)
lives in the handler + repository and is covered by the handler/integration tests;
here the in-memory status checks and event emission are what's under test.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.domain.invitation.entity import Invitation, effective_status, is_expired
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


# ── S-019: the status a reader is told ──────────────────────────────────────────


def test_effective_status_reports_a_timed_out_pending_as_expired() -> None:
    """The defect, at its smallest. Nothing sweeps the row, so the stored value is
    ``pending``; what a reader must be told is ``expired``."""
    now = datetime.now(UTC)
    assert effective_status("pending", now - timedelta(seconds=1), now=now) == "expired"


def test_effective_status_leaves_a_live_pending_alone() -> None:
    """The control: the failing reading and the passing reading are different words."""
    now = datetime.now(UTC)
    assert effective_status("pending", now + timedelta(days=1), now=now) == "pending"


def test_effective_status_reports_terminal_statuses_verbatim() -> None:
    """``accepted`` and ``revoked`` record an act, not a deadline, so the clock passing
    afterwards must not relabel them."""
    now = datetime.now(UTC)
    long_gone = now - timedelta(days=365)
    assert effective_status("accepted", long_gone, now=now) == "accepted"
    assert effective_status("revoked", long_gone, now=now) == "revoked"
    assert effective_status("expired", long_gone, now=now) == "expired"


def test_effective_status_treats_a_missing_deadline_as_never_expiring() -> None:
    """``expires_at`` is nullable on the entity. No deadline is not a passed deadline —
    and ``accept`` reads it the same way, which is the point of the shared predicate."""
    now = datetime.now(UTC)
    assert effective_status("pending", None, now=now) == "pending"
    assert is_expired(None, now=now) is False


def test_the_read_and_accept_agree_at_the_exact_boundary() -> None:
    """One predicate, so the two halves cannot disagree — asserted rather than assumed.

    At ``expires_at == now`` the invitation is NOT yet expired: ``accept`` succeeds and
    the read still says ``pending``. One second later both flip. The instant either half
    is given its own comparison, this is the test that catches it.
    """
    now = datetime.now(UTC)

    # Exactly at the deadline: accept succeeds, so the read must not say "expired".
    at_deadline = _pending(expires_at=now)
    at_deadline.accept(user_id=uuid.uuid4(), user_email="invited@x.com", now=now)
    assert at_deadline.status == "accepted"
    assert effective_status("pending", now, now=now) == "pending"

    # One second past it: accept refuses, and the read says "expired".
    past = _pending(expires_at=now - timedelta(seconds=1))
    with pytest.raises(ConflictError, match="expired"):
        past.accept(user_id=uuid.uuid4(), user_email="invited@x.com", now=now)
    assert effective_status("pending", now - timedelta(seconds=1), now=now) == "expired"
