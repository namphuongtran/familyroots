"""SQLAlchemy implementation of the invitation repository."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import desc, select, update
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
        result = await self._session.execute(
            select(ClanInvitation).where(
                ClanInvitation.clan_id == clan_id,
                ClanInvitation.email == email,
                ClanInvitation.status == "pending",
            )
        )
        return result.scalar_one_or_none()

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

    async def get_by_id(self, invitation_id: uuid.UUID, clan_id: uuid.UUID) -> Invitation | None:
        result = await self._session.execute(
            select(ClanInvitation).where(
                ClanInvitation.id == invitation_id,
                ClanInvitation.clan_id == clan_id,
            )
        )
        model = result.scalar_one_or_none()
        return to_domain(model) if model else None
