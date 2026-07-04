"""Invitation use-case handlers (clan-context pattern: transient AggregateRoot + events)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.application.invitation.commands import (
    AcceptInvitation,
    CreateInvitation,
    RevokeInvitation,
)
from app.core.config import settings
from app.domain.invitation.events import (
    InvitationAccepted,
    InvitationCreated,
    InvitationRevoked,
)
from app.domain.invitation.repository import InvitationRepository
from app.domain.shared.entity import AggregateRoot
from app.domain.shared.exceptions import ConflictError, EntityNotFoundError, ForbiddenError
from app.domain.shared.unit_of_work import UnitOfWork


class InvitationCommandHandler:
    def __init__(self, repo: InvitationRepository, uow: UnitOfWork) -> None:
        self._repo = repo
        self._uow = uow

    async def create(self, cmd: CreateInvitation) -> dict[str, Any]:
        email = cmd.email.strip().lower()
        if await self._repo.get_pending_by_email(cmd.clan_id, email):
            raise ConflictError("invitation.pending_exists")

        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(days=settings.INVITATION_TTL_DAYS)
        invitation_id = await self._repo.create_invitation(
            clan_id=cmd.clan_id,
            email=email,
            role=cmd.role,
            invited_by=cmd.actor.user_id,
            token=token,
            expires_at=expires_at,
        )

        agg = AggregateRoot()
        agg.add_event(
            InvitationCreated(
                clan_id=cmd.clan_id,
                actor_id=cmd.actor.user_id,
                actor_role=cmd.actor.role,
                resource_id=invitation_id,
                email=email,
                invited_role=cmd.role,
            )
        )
        self._uow.track(agg)
        await self._uow.commit()
        return {
            "id": invitation_id,
            "email": email,
            "role": cmd.role,
            "token": token,
            "expires_at": expires_at,
            "accept_path": f"/api/v1/invitations/{token}/accept",
        }

    async def accept(self, cmd: AcceptInvitation) -> dict[str, Any]:
        inv = await self._repo.get_by_token(cmd.token)
        if not inv:
            raise EntityNotFoundError("invitation.not_found")
        if inv.status != "pending":
            raise ConflictError("invitation.not_pending")
        if inv.expires_at < datetime.now(UTC):
            raise ConflictError("invitation.expired")
        if inv.email.strip().lower() != cmd.user_email.strip().lower():
            raise ForbiddenError("invitation.email_mismatch")

        # Claim the invitation atomically BEFORE any membership work: if a
        # concurrent revoke (or another accept) already moved it out of
        # "pending", we stop here with the contract's 409 and the transaction
        # never grants anything.
        claimed = await self._repo.transition_status(
            inv.id,
            expected="pending",
            to="accepted",
            accepted_by=cmd.user_id,
            accepted_at=datetime.now(UTC),
        )
        if not claimed:
            raise ConflictError("invitation.not_pending")

        await self._repo.ensure_profile(cmd.user_id, cmd.user_email, cmd.user_full_name)

        existing = await self._repo.get_user_role(cmd.user_id, inv.clan_id)
        if existing and existing.is_approved:
            raise ConflictError("invitation.already_member")
        if existing and not existing.is_approved:
            # Promote the pending self-request to approved with the invited role.
            existing.role = inv.role
            existing.is_approved = True
            existing.approved_by = inv.invited_by
            existing.approved_at = datetime.now(UTC)
        else:
            self._repo.add_membership(
                clan_id=inv.clan_id,
                user_id=cmd.user_id,
                role=inv.role,
                approved_by=inv.invited_by,
                approved_at=datetime.now(UTC),
            )

        agg = AggregateRoot()
        agg.add_event(
            InvitationAccepted(
                clan_id=inv.clan_id,
                actor_id=cmd.user_id,
                actor_role=inv.role,
                resource_id=inv.id,
                email=inv.email,
            )
        )
        self._uow.track(agg)
        await self._uow.commit()
        return {"clan_id": inv.clan_id, "role": inv.role}

    async def revoke(self, cmd: RevokeInvitation) -> None:
        inv = await self._repo.get_by_id(cmd.invitation_id, cmd.clan_id)
        if not inv:
            raise EntityNotFoundError("invitation.not_found")
        if inv.status != "pending":
            raise ConflictError("invitation.not_pending")
        # Atomic guard: an accept that committed after our read wins the row;
        # per owner decision (2026-07-04) revoke-after-accept is a 409 and
        # membership removal stays in member management.
        claimed = await self._repo.transition_status(inv.id, expected="pending", to="revoked")
        if not claimed:
            raise ConflictError("invitation.not_pending")

        agg = AggregateRoot()
        agg.add_event(
            InvitationRevoked(
                clan_id=cmd.clan_id,
                actor_id=cmd.actor.user_id,
                actor_role=cmd.actor.role,
                resource_id=inv.id,
            )
        )
        self._uow.track(agg)
        await self._uow.commit()


class InvitationQueryHandler:
    def __init__(self, repo: InvitationRepository) -> None:
        self._repo = repo

    async def list_for_clan(self, clan_id: uuid.UUID) -> list[Any]:
        return await self._repo.list_by_clan(clan_id)
