"""SQLAlchemy implementation of the invitation repository."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.invitation.entity import Invitation
from app.domain.invitation.repository import InvitationRepository
from app.infrastructure.persistence._profile import ensure_profile_row
from app.infrastructure.persistence.invitation_mapper import to_domain
from app.models.clan_invitation import ClanInvitation
from app.models.user_clan_role import UserClanRole


class SqlAlchemyInvitationRepository(InvitationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_pending_by_email(self, clan_id: uuid.UUID, email: str) -> ClanInvitation | None:
        """A LIVE pending invitation only — a timed-out (expires_at <= now) row is not a
        blocker (it is lazily retired by ``expire_stale_pending`` on the re-invite path)."""
        result = await self._session.execute(
            select(ClanInvitation).where(
                ClanInvitation.clan_id == clan_id,
                ClanInvitation.email == email,
                ClanInvitation.status == "pending",
                ClanInvitation.expires_at > func.now(),
            )
        )
        return result.scalar_one_or_none()

    async def expire_stale_pending(self, clan_id: uuid.UUID, email: str) -> int:
        """Transition a timed-out (expires_at <= now) ``pending`` invitation for this
        (clan, email) to ``expired``. DB-side ``now()`` for one clock. Returns the row
        count (0 or 1 — the partial unique index ``uq_clan_invitations_pending`` allows at
        most one pending per pair). Frees that unique slot so a fresh invite can insert."""
        result = await self._session.execute(
            update(ClanInvitation)
            .where(
                ClanInvitation.clan_id == clan_id,
                ClanInvitation.email == email,
                ClanInvitation.status == "pending",
                ClanInvitation.expires_at <= func.now(),
            )
            .values(status="expired")
        )
        return result.rowcount

    async def get_by_token(self, token: str) -> Invitation | None:
        result = await self._session.execute(
            select(ClanInvitation).where(ClanInvitation.token == token)
        )
        model = result.scalar_one_or_none()
        return to_domain(model) if model else None

    async def create_invitation(
        self,
        *,
        invitation_id: uuid.UUID,
        clan_id: uuid.UUID,
        email: str,
        role: str,
        invited_by: uuid.UUID,
        token: str,
        expires_at: datetime,
    ) -> None:
        self._session.add(
            ClanInvitation(
                id=invitation_id,
                clan_id=clan_id,
                email=email,
                role=role,
                invited_by=invited_by,
                token=token,
                expires_at=expires_at,
                status="pending",
            )
        )
        await self._session.flush()  # surface unique-token / FK violations in-request

    async def list_by_clan(self, clan_id: uuid.UUID) -> list[ClanInvitation]:
        result = await self._session.execute(
            select(ClanInvitation)
            .where(ClanInvitation.clan_id == clan_id)
            .order_by(desc(ClanInvitation.created_at))
        )
        return list(result.scalars().all())

    async def ensure_profile(
        self, user_id: uuid.UUID, email: str, display_name: str | None
    ) -> None:
        await ensure_profile_row(self._session, user_id, email, display_name)

    async def get_user_role(self, user_id: uuid.UUID, clan_id: uuid.UUID) -> UserClanRole | None:
        result = await self._session.execute(
            select(UserClanRole).where(
                UserClanRole.user_id == user_id,
                UserClanRole.clan_id == clan_id,
            )
        )
        return result.scalar_one_or_none()

    async def transition_status(
        self,
        invitation_id: uuid.UUID,
        *,
        expected: str,
        to: str,
        accepted_by: uuid.UUID | None = None,
        accepted_at: datetime | None = None,
    ) -> bool:
        values: dict[str, object] = {"status": to}
        if accepted_by is not None:
            values["accepted_by"] = accepted_by
        if accepted_at is not None:
            values["accepted_at"] = accepted_at
        result = await self._session.execute(
            update(ClanInvitation)
            .where(ClanInvitation.id == invitation_id, ClanInvitation.status == expected)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return bool(result.rowcount)

    def add_membership(
        self,
        *,
        clan_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        approved_by: uuid.UUID,
        approved_at: datetime,
    ) -> None:
        self._session.add(
            UserClanRole(
                clan_id=clan_id,
                user_id=user_id,
                role=role,
                is_approved=True,
                approved_by=approved_by,
                approved_at=approved_at,
            )
        )

    async def promote_if_pending(
        self,
        ucr_id: uuid.UUID,
        *,
        role: str,
        approved_by: uuid.UUID,
        approved_at: datetime,
    ) -> bool:
        """Atomically promote a STILL-PENDING membership to approved; return whether it
        won. Conditional UPDATE (``WHERE id = :id AND is_approved = false``) so a
        concurrent reject/remove that deleted the pending self-request, or a concurrent
        approve, makes accept's promote match 0 rows (the caller re-resolves) instead of
        a 0-row ORM UPDATE -> StaleDataError -> 500. ``synchronize_session=False`` — the
        pre-read ORM instance is not reused after this write."""
        result = await self._session.execute(
            update(UserClanRole)
            .where(UserClanRole.id == ucr_id, UserClanRole.is_approved.is_(False))
            .values(role=role, is_approved=True, approved_by=approved_by, approved_at=approved_at)
            .returning(UserClanRole.id)
            .execution_options(synchronize_session=False)
        )
        return result.scalar_one_or_none() is not None

    async def membership_is_approved(self, ucr_id: uuid.UUID) -> bool | None:
        """Truthful current approval state of a membership BY ID: None if the row is
        gone, else its ``is_approved``. Column select (not entity) so it bypasses the
        identity map — the pre-read ORM instance carries a stale ``is_approved`` — used
        to distinguish 'pending row removed' (grant fresh) from 'approved concurrently'
        (already_member) after a lost ``promote_if_pending``."""
        result = await self._session.execute(
            select(UserClanRole.is_approved).where(UserClanRole.id == ucr_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, invitation_id: uuid.UUID, clan_id: uuid.UUID) -> Invitation | None:
        result = await self._session.execute(
            select(ClanInvitation).where(
                ClanInvitation.id == invitation_id,
                ClanInvitation.clan_id == clan_id,
            )
        )
        model = result.scalar_one_or_none()
        return to_domain(model) if model else None
