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
from app.application.invitation.views import InvitationListItem
from app.core.config import settings
from app.domain.invitation.entity import Invitation, effective_status
from app.domain.invitation.repository import InvitationRepository
from app.domain.shared.exceptions import ConflictError, EntityNotFoundError
from app.domain.shared.unit_of_work import UnitOfWork


class InvitationCommandHandler:
    def __init__(self, repo: InvitationRepository, uow: UnitOfWork) -> None:
        self._repo = repo
        self._uow = uow

    async def create(self, cmd: CreateInvitation) -> dict[str, Any]:
        email = cmd.email.strip().lower()
        # Lazily retire a timed-out prior invite for this (clan, email) so it neither
        # blocks re-invite (get_pending_by_email is now live-only) nor collides on the
        # partial unique index. Committed atomically with the new invite below.
        await self._repo.expire_stale_pending(cmd.clan_id, email)
        if await self._repo.get_pending_by_email(cmd.clan_id, email):
            raise ConflictError("invitation.pending_exists")

        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(days=settings.INVITATION_TTL_DAYS)
        inv = Invitation.create(
            clan_id=cmd.clan_id,
            email=email,
            role=cmd.role,
            invited_by=cmd.actor.user_id,
            token=token,
            expires_at=expires_at,
            actor=cmd.actor,
        )
        await self._repo.create_invitation(
            invitation_id=inv.id,
            clan_id=inv.clan_id,
            email=inv.email,
            role=inv.role,
            invited_by=inv.invited_by,
            token=token,
            expires_at=expires_at,
        )
        self._uow.track(inv)
        await self._uow.commit()
        return {
            "id": inv.id,
            "email": inv.email,
            "role": inv.role,
            "token": inv.token,
            "expires_at": expires_at,
            "accept_path": f"/api/v1/invitations/{token}/accept",
        }

    async def accept(self, cmd: AcceptInvitation) -> dict[str, Any]:
        inv = await self._repo.get_by_token(cmd.token)
        if inv is None:
            raise EntityNotFoundError("invitation.not_found")

        # Aggregate validates the domain preconditions (pending / not expired / email
        # matches) and buffers the InvitationAccepted event. The buffer is only
        # dispatched if we track the aggregate below — which we do ONLY after the
        # atomic claim succeeds.
        now = datetime.now(UTC)
        inv.accept(user_id=cmd.user_id, user_email=cmd.user_email, now=now)

        # The authoritative accept-vs-revoke race guard (C3): a conditional UPDATE
        # that writes nothing if a concurrent revoke/accept already left "pending".
        # A lost race raises here — the aggregate is never tracked, so its buffered
        # event is discarded and the transaction grants nothing.
        claimed = await self._repo.transition_status(
            inv.id,
            expected="pending",
            to="accepted",
            accepted_by=cmd.user_id,
            accepted_at=now,
        )
        if not claimed:
            raise ConflictError("invitation.not_pending")

        await self._repo.ensure_profile(cmd.user_id, cmd.user_email, cmd.user_full_name)

        existing = await self._repo.get_user_role(cmd.user_id, inv.clan_id)
        if existing and existing.is_approved:
            raise ConflictError("invitation.already_member")
        if existing:
            # Promote the pending self-request atomically. A concurrent reject/remove
            # that deleted it, or a concurrent approve, makes this match 0 rows (instead
            # of a 0-row ORM UPDATE -> StaleDataError -> 500); re-resolve by the exact id.
            if not await self._repo.promote_if_pending(
                existing.id, role=inv.role, approved_by=inv.invited_by, approved_at=now
            ):
                # Promote lost: the row is no longer the pending one we read. If it
                # still EXISTS (approved concurrently) treat it as already_member — a
                # fresh INSERT would collide on the (user_id, clan_id) unique index.
                # Only a row that was removed (state is None) frees us to grant fresh.
                if await self._repo.membership_is_approved(existing.id) is not None:
                    raise ConflictError("invitation.already_member")
                # The pending row was removed concurrently — the invitation is still
                # valid, so grant a fresh approved membership.
                self._repo.add_membership(
                    clan_id=inv.clan_id,
                    user_id=cmd.user_id,
                    role=inv.role,
                    approved_by=inv.invited_by,
                    approved_at=now,
                )
        else:
            self._repo.add_membership(
                clan_id=inv.clan_id,
                user_id=cmd.user_id,
                role=inv.role,
                approved_by=inv.invited_by,
                approved_at=now,
            )

        self._uow.track(inv)  # claim won → dispatch InvitationAccepted on commit
        await self._uow.commit()
        return {"clan_id": inv.clan_id, "role": inv.role}

    async def revoke(self, cmd: RevokeInvitation) -> None:
        inv = await self._repo.get_by_id(cmd.invitation_id, cmd.clan_id)
        if inv is None:
            raise EntityNotFoundError("invitation.not_found")

        # Aggregate validates + buffers InvitationRevoked; dispatched only if the
        # atomic claim below wins.
        inv.revoke(cmd.actor)

        # Atomic guard: an accept that committed after our read wins the row;
        # per owner decision (2026-07-04) revoke-after-accept is a 409 and
        # membership removal stays in member management.
        claimed = await self._repo.transition_status(inv.id, expected="pending", to="revoked")
        if not claimed:
            raise ConflictError("invitation.not_pending")

        self._uow.track(inv)  # claim won → dispatch InvitationRevoked on commit
        await self._uow.commit()


class InvitationQueryHandler:
    def __init__(self, repo: InvitationRepository) -> None:
        self._repo = repo

    async def list_for_clan(self, clan_id: uuid.UUID) -> list[InvitationListItem]:
        """A clan's invitations, newest first, with a status that agrees with ``expires_at``.

        The stored ``status`` is not reported as-is. Nothing sweeps the table, so a
        timed-out row stays ``pending`` in storage until the next create for that
        (clan, email) retires it — and a list that repeated that would show an admin
        ``Đang chờ`` for a link ``accept`` already refuses (S-019).

        ``datetime.now(UTC)`` is deliberately the SAME clock ``accept`` reads
        (``InvitationCommandHandler.accept`` above), not the DB-side ``now()`` that
        ``expire_stale_pending`` uses. What this read has to agree with is the accept
        decision, so it must be compared against the accept decision's clock.

        Read once, outside the loop, so every row in one response is judged against one
        instant rather than against the clock as it moves down the list.
        """
        now = datetime.now(UTC)
        return [
            InvitationListItem(
                id=row.id,
                clan_id=row.clan_id,
                email=row.email,
                role=row.role,
                status=effective_status(row.status, row.expires_at, now=now),
                expires_at=row.expires_at,
                accepted_at=row.accepted_at,
                created_at=row.created_at,
            )
            for row in await self._repo.list_by_clan(clan_id)
        ]
