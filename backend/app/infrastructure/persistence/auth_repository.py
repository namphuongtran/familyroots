"""SQLAlchemy implementations for Auth bounded context."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import exists, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auth.repository import (
    AuthProfileView,
    AuthQueryPort,
    AuthRepository,
    FCMTokenRepository,
)
from app.infrastructure.persistence._profile import ensure_profile_row
from app.models.clan import Clan
from app.models.user_clan_role import UserClanRole
from app.models.user_profile import UserProfile as UserProfileModel


def _profile_view(row: Any | None) -> AuthProfileView | None:
    """Map a (UserProfile, UserClanRole|None, Clan|None) row to the typed read
    model — positional unpacking matches the select() order, so the mapping does
    not depend on ORM class names (the old ``row.<ClassName>`` access did, and
    broke at runtime when the alias didn't match the mapped class name)."""
    if row is None:
        return None
    profile, membership, clan = row
    return AuthProfileView(
        person_id=profile.person_id,
        clan_id=membership.clan_id if membership else None,
        clan_name=clan.name if clan else None,
        role=membership.role if membership else None,
        is_approved=bool(membership and membership.is_approved),
    )


class SqlAlchemyAuthRepository(AuthRepository):
    """SQLAlchemy implementation of Auth write persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_clan_by_slug(self, slug: str) -> Clan | None:
        result = await self._session.execute(select(Clan).where(Clan.slug == slug))
        return result.scalar_one_or_none()

    async def get_clan_by_id(self, clan_id: uuid.UUID) -> Clan | None:
        return await self._session.get(Clan, clan_id)

    async def get_user_role(self, user_id: uuid.UUID, clan_id: uuid.UUID) -> UserClanRole | None:
        result = await self._session.execute(
            select(UserClanRole).where(
                UserClanRole.user_id == user_id,
                UserClanRole.clan_id == clan_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_clan(self, *, name: str, slug: str) -> uuid.UUID:
        clan = Clan(name=name, slug=slug)
        self._session.add(clan)
        await self._session.flush()  # INSERT so the membership FK (and callers) get the id
        return clan.id

    def add_membership(
        self,
        *,
        clan_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        is_approved: bool,
        approved_by: uuid.UUID | None = None,
        approved_at: datetime | None = None,
    ) -> None:
        self._session.add(
            UserClanRole(
                clan_id=clan_id,
                user_id=user_id,
                role=role,
                is_approved=is_approved,
                approved_by=approved_by,
                approved_at=approved_at,
            )
        )

    async def ensure_profile(
        self, user_id: uuid.UUID, email: str, display_name: str | None
    ) -> None:
        await ensure_profile_row(self._session, user_id, email, display_name)


class SqlAlchemyAuthQueryPort(AuthQueryPort):
    """SQLAlchemy implementation of Auth read persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_profile(self, user_id: uuid.UUID) -> AuthProfileView | None:
        result = await self._session.execute(
            select(UserProfileModel, UserClanRole, Clan)
            .outerjoin(
                UserClanRole,
                (UserProfileModel.id == UserClanRole.user_id) & UserClanRole.is_approved.is_(True),
            )
            .outerjoin(Clan, UserClanRole.clan_id == Clan.id)
            .where(UserProfileModel.id == user_id)
            # Deterministic for multi-clan users: oldest approved membership,
            # clan_id as a stable tiebreak. Bare LIMIT 1 returned an arbitrary row.
            .order_by(UserClanRole.created_at.asc().nulls_last(), UserClanRole.clan_id)
            .limit(1)
        )
        return _profile_view(result.first())

    async def get_login_profile(self, user_id: uuid.UUID) -> AuthProfileView | None:
        result = await self._session.execute(
            select(UserProfileModel, UserClanRole, Clan)
            .outerjoin(UserClanRole, UserProfileModel.id == UserClanRole.user_id)
            .outerjoin(Clan, UserClanRole.clan_id == Clan.id)
            .where(UserProfileModel.id == user_id)
            # Approved membership always beats a pending one (a user approved in
            # clan A but pending in clan B must log in as A, not "B, role null"),
            # then oldest first, clan_id tiebreak — bare LIMIT 1 was arbitrary.
            .order_by(
                UserClanRole.is_approved.desc().nulls_last(),
                UserClanRole.created_at.asc().nulls_last(),
                UserClanRole.clan_id,
            )
            .limit(1)
        )
        return _profile_view(result.first())

    async def has_pending_membership(self, user_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(
                exists().where(
                    UserClanRole.user_id == user_id,
                    UserClanRole.is_approved.is_(False),
                )
            )
        )
        return bool(result.scalar())

    async def is_account_active(self, user_id: uuid.UUID) -> bool | None:
        return await self._session.scalar(
            select(UserProfileModel.is_active).where(UserProfileModel.id == user_id)
        )


class SqlAlchemyFCMTokenRepository(FCMTokenRepository):
    """SQLAlchemy implementation of FCM Token repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register_token(self, user_id: str, token: str, device_platform: str) -> None:
        await self._session.execute(
            text("""
                INSERT INTO public.user_fcm_tokens (user_id, token, device_platform)
                VALUES (:user_id, :token, :platform)
                ON CONFLICT (token) DO UPDATE
                SET user_id = :user_id, device_platform = :platform, updated_at = NOW()
            """),
            {"user_id": user_id, "token": token, "platform": device_platform},
        )

    async def remove_token(self, user_id: str, token: str) -> None:
        await self._session.execute(
            text("DELETE FROM public.user_fcm_tokens WHERE user_id = :user_id AND token = :token"),
            {"user_id": user_id, "token": token},
        )
