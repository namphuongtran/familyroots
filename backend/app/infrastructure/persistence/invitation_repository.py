"""SQLAlchemy implementation of the invitation repository."""

from __future__ import annotations

import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.invitation.repository import InvitationRepository
from app.models.clan_invitation import ClanInvitation
from app.models.user_clan_role import UserClanRole
from app.models.user_profile import UserProfile


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

    async def get_by_token(self, token: str) -> ClanInvitation | None:
        result = await self._session.execute(
            select(ClanInvitation).where(ClanInvitation.token == token)
        )
        return result.scalar_one_or_none()

    def add_invitation(self, invitation: ClanInvitation) -> None:
        self._session.add(invitation)

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
        existing = await self._session.get(UserProfile, user_id)
        if existing is not None:
            return
        self._session.add(
            UserProfile(id=user_id, email=email, display_name=display_name or email.split("@")[0])
        )
        await self._session.flush()

    async def get_user_role(self, user_id: uuid.UUID, clan_id: uuid.UUID) -> UserClanRole | None:
        result = await self._session.execute(
            select(UserClanRole).where(
                UserClanRole.user_id == user_id,
                UserClanRole.clan_id == clan_id,
            )
        )
        return result.scalar_one_or_none()

    def add_user_role(self, role: UserClanRole) -> None:
        self._session.add(role)
