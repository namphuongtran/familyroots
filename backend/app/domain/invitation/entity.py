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
        if self.expires_at is not None and self.expires_at < now:
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
