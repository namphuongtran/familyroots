"""SQLAlchemy adapter for deleting a user's own account (ADR-079).

Bound to the privileged system session by the composition root: the account spans
every clan it belongs to, ``user_clan_roles`` DELETE is clan-keyed for the request role
and ``identity_claims`` is deny-all for it (ADR-042, ADR-050). Every statement here is
keyed on the caller's own user id, taken from the verified token, never from input.
"""

from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auth.repository import RemovedRole
from app.models.identity_claim import IdentityClaim
from app.models.user_clan_role import UserClanRole
from app.models.user_fcm_token import UserFcmToken
from app.models.user_profile import UserProfile

# The reserved domain (RFC 2606) a deleted account's email is replaced with. The column
# is NOT NULL and unique, so each tombstone gets its own address built from the id.
_TOMBSTONE_DOMAIN = "deleted.invalid"


def tombstone_email(user_id: uuid.UUID) -> str:
    return f"deleted-{user_id}@{_TOMBSTONE_DOMAIN}"


class SqlAlchemyAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_clans_where_last_admin(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        my_admin_clans = select(UserClanRole.clan_id).where(
            UserClanRole.user_id == user_id,
            UserClanRole.role == "admin",
            UserClanRole.is_approved.is_(True),
        )
        # The same rows lock_admin_count locks, in the same (id) order, so this
        # serializes with a concurrent demote/remove instead of racing it.
        rows = await self._session.execute(
            select(UserClanRole.id, UserClanRole.clan_id)
            .where(
                UserClanRole.clan_id.in_(my_admin_clans),
                UserClanRole.role == "admin",
                UserClanRole.is_approved.is_(True),
            )
            .order_by(UserClanRole.id)
            .with_for_update()
        )
        admins = Counter(clan_id for _, clan_id in rows.all())
        return sorted(clan_id for clan_id, n in admins.items() if n <= 1)

    async def remove_roles(self, user_id: uuid.UUID) -> list[RemovedRole]:
        result = await self._session.execute(
            delete(UserClanRole)
            .where(UserClanRole.user_id == user_id)
            .returning(UserClanRole.clan_id, UserClanRole.role)
        )
        return sorted(
            (RemovedRole(clan_id=clan_id, role=role) for clan_id, role in result.all()),
            key=lambda r: r.clan_id,
        )

    async def remove_claims_and_push_tokens(self, user_id: uuid.UUID) -> None:
        await self._session.execute(delete(IdentityClaim).where(IdentityClaim.user_id == user_id))
        await self._session.execute(delete(UserFcmToken).where(UserFcmToken.user_id == user_id))

    async def tombstone_profile(self, user_id: uuid.UUID) -> bool:
        placeholder = tombstone_email(user_id)
        result = await self._session.execute(
            update(UserProfile)
            .where(UserProfile.id == user_id, UserProfile.email != placeholder)
            .values(
                email=placeholder,
                display_name=None,
                avatar_url=None,
                person_id=None,
                last_login_at=None,
                platform_role="user",
                is_active=False,
            )
            .execution_options(synchronize_session=False)
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]
