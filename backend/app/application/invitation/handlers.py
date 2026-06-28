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
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.models.clan_invitation import ClanInvitation
from app.models.user_clan_role import UserClanRole


class InvitationCommandHandler:
    def __init__(self, repo: InvitationRepository, uow: SqlAlchemyUnitOfWork) -> None:
        self._repo = repo
        self._uow = uow

    async def create(self, cmd: CreateInvitation) -> dict[str, Any]:
        email = cmd.email.strip().lower()
        if await self._repo.get_pending_by_email(cmd.clan_id, email):
            raise ConflictError("invitation.pending_exists")

        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(days=settings.INVITATION_TTL_DAYS)
        inv = ClanInvitation(
            clan_id=cmd.clan_id,
            email=email,
            role=cmd.role,
            invited_by=cmd.actor.user_id,
            token=token,
            expires_at=expires_at,
            status="pending",
        )
        self._repo.add_invitation(inv)
        await self._uow.flush()

        agg = AggregateRoot()
        agg.add_event(
            InvitationCreated(
                clan_id=cmd.clan_id,
                actor_id=cmd.actor.user_id,
                actor_role=cmd.actor.role,
                resource_id=inv.id,
                email=email,
                invited_role=cmd.role,
            )
        )
        self._uow.track(agg)
        await self._uow.commit()
        return {
            "id": inv.id,
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
            self._repo.add_user_role(
                UserClanRole(
                    clan_id=inv.clan_id,
                    user_id=cmd.user_id,
                    role=inv.role,
                    is_approved=True,
                    approved_by=inv.invited_by,
                    approved_at=datetime.now(UTC),
                )
            )

        inv.status = "accepted"
        inv.accepted_by = cmd.user_id
        inv.accepted_at = datetime.now(UTC)

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
        inv.status = "revoked"

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
