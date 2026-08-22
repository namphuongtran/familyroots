"""Invitation domain entity — pure Python, no framework dependencies.

The Invitation aggregate owns the clan-invitation lifecycle (create → accept /
revoke) and the invariants that govern each transition. It mirrors the Person and
Clan aggregates: behavior emits domain events for audit logging.

IMPORTANT — concurrency: the in-memory ``status`` checks here are fast, friendly-error
prechecks only. The authoritative accept-vs-revoke race guard is the DB-side atomic
``transition_status`` compare-and-swap in the repository (C3, seam-review-2026-07-04).
The handler runs that CAS and only tracks this aggregate (so its event is dispatched)
once the claim succeeds — a lost race discards the buffered event.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.invitation.events import (
    InvitationAccepted,
    InvitationCreated,
    InvitationRevoked,
)
from app.domain.shared.entity import AggregateRoot
from app.domain.shared.exceptions import ConflictError, ForbiddenError
from app.domain.shared.value_objects import ActorInfo


def is_expired(expires_at: datetime | None, *, now: datetime) -> bool:
    """Whether an invitation whose deadline is ``expires_at`` has timed out at ``now``.

    ONE predicate, two callers, on purpose (S-019). ``accept`` below refuses on it, and
    the read side derives the reported status from it. If the two ever disagree, a list
    reports ``pending`` for an invitation that ``accept`` refuses — which is the exact
    defect S-019 closed. Keeping the comparison in one function is what stops them
    drifting apart again.
    """
    return expires_at is not None and expires_at < now


def effective_status(status: str, expires_at: datetime | None, *, now: datetime) -> str:
    """The status a reader is told, which is not always the stored one.

    Nothing sweeps ``clan_invitations``: a timed-out row keeps ``status = 'pending'``
    until the next create for that (clan, email) lazily retires it (see
    ``InvitationRepository.expire_stale_pending``). So the read derives instead — a
    stored ``pending`` past its ``expires_at`` reads as ``expired``.

    Only ``pending`` derives. ``accepted``, ``revoked``, and an already-stored
    ``expired`` are terminal facts about what somebody did, not about the clock, so
    they are reported verbatim however long ago ``expires_at`` passed.
    """
    if status == "pending" and is_expired(expires_at, now=now):
        return "expired"
    return status


@dataclass
class Invitation(AggregateRoot):
    """Clan invitation aggregate root."""

    clan_id: uuid.UUID = field(default_factory=uuid.uuid4)
    email: str = ""
    role: str = ""
    token: str = ""
    status: str = "pending"
    invited_by: uuid.UUID = field(default_factory=uuid.uuid4)
    expires_at: datetime | None = None
    accepted_by: uuid.UUID | None = None
    accepted_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        clan_id: uuid.UUID,
        email: str,
        role: str,
        invited_by: uuid.UUID,
        token: str,
        expires_at: datetime,
        actor: ActorInfo,
    ) -> Invitation:
        """Factory for a new pending invitation. Emits InvitationCreated.

        Token generation and TTL are infrastructure/config concerns computed by the
        caller and passed in, so the domain stays framework-agnostic.
        """
        inv = cls(
            clan_id=clan_id,
            email=email,
            role=role,
            token=token,
            invited_by=invited_by,
            expires_at=expires_at,
            status="pending",
        )
        inv.add_event(
            InvitationCreated(
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                resource_id=inv.id,
                email=email,
                invited_role=role,
            )
        )
        return inv

    def accept(self, *, user_id: uuid.UUID, user_email: str, now: datetime) -> None:
        """Accept the invitation on behalf of ``user_id``. Emits InvitationAccepted.

        Validates the domain preconditions (pending, not expired, email matches). The
        actual status write is the repository's atomic CAS — see the module docstring.
        """
        if self.status != "pending":
            raise ConflictError("invitation.not_pending")
        if is_expired(self.expires_at, now=now):
            raise ConflictError("invitation.expired")
        if self.email.strip().lower() != user_email.strip().lower():
            raise ForbiddenError("invitation.email_mismatch")

        self.status = "accepted"
        self.accepted_by = user_id
        self.accepted_at = now
        self.add_event(
            InvitationAccepted(
                clan_id=self.clan_id,
                actor_id=user_id,
                actor_role=self.role,
                resource_id=self.id,
                email=self.email,
            )
        )

    def revoke(self, actor: ActorInfo) -> None:
        """Revoke a pending invitation. Emits InvitationRevoked."""
        if self.status != "pending":
            raise ConflictError("invitation.not_pending")

        self.status = "revoked"
        self.add_event(
            InvitationRevoked(
                clan_id=self.clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                resource_id=self.id,
            )
        )
