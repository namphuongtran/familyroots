"""SQLAlchemy implementation of ClanRepository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.pagination import build_page, paginate_query
from app.domain.clan.entity import Clan as ClanEntity
from app.infrastructure.persistence.clan_mapper import apply_to_orm, to_domain
from app.models.clan import Clan
from app.models.clan_membership import ClanMembership
from app.models.person import Person
from app.models.user_clan_role import UserClanRole


class SqlAlchemyClanRepository:
    """ClanRepository backed by SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_clan(self, clan_id: uuid.UUID) -> Clan | None:
        return await self._session.get(Clan, clan_id)

    async def get_user_clan_role(
        self, clan_id: uuid.UUID, user_id: uuid.UUID
    ) -> UserClanRole | None:
        result = await self._session.execute(
            select(UserClanRole).where(
                UserClanRole.clan_id == clan_id, UserClanRole.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def lock_admin_count(self, clan_id: uuid.UUID) -> int:
        """Lock the clan's approved-admin rows and return their count.

        FOR UPDATE serializes every operation that could reduce the admin set;
        the second concurrent reducer re-reads post-commit state and sees the
        true remaining count (C1 last-admin race, ADR spec 2026-07-12)."""
        result = await self._session.execute(
            select(UserClanRole.id)
            .where(
                UserClanRole.clan_id == clan_id,
                UserClanRole.role == "admin",
                UserClanRole.is_approved.is_(True),
            )
            # Deterministic lock order: concurrent reducers acquire the row locks
            # in the same sequence, so they serialize but can never deadlock.
            .order_by(UserClanRole.id)
            .with_for_update()
        )
        return len(result.scalars().all())

    async def list_users(
        self,
        clan_id: uuid.UUID,
        approved: bool = True,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List users with pagination. Returns a page dict.

        Eagerly LEFT JOINs ``user_profiles`` (via the ``UserClanRole.user_profile``
        relationship, keyed on ``user_profiles.id == user_clan_roles.user_id``) so
        callers can read each row's linked ``person_id`` without a second query or
        an ``AttributeError`` on the raw ``UserClanRole`` row. ``joinedload`` keeps
        cursor pagination intact: it only changes how ``UserClanRole.user_profile``
        is populated, not the entities/columns the query returns, and a many-to-one
        eager join never duplicates rows under ``LIMIT``. Users without a profile
        (should not normally happen, but the join must not hide them) still come
        back with ``user_profile is None``.
        """
        query = (
            select(UserClanRole)
            .options(joinedload(UserClanRole.user_profile))
            .where(
                UserClanRole.clan_id == clan_id,
                UserClanRole.is_approved.is_(approved),
            )
        )
        capped = min(limit, 100)
        query = paginate_query(query, UserClanRole, cursor, capped)
        result = await self._session.execute(query)
        items = list(result.scalars().all())
        return build_page(items, capped)

    async def get_clan_stats(self, clan_id: uuid.UUID) -> dict[str, int]:
        total_users_result = await self._session.execute(
            select(func.count()).where(UserClanRole.clan_id == clan_id)
        )
        approved_users_result = await self._session.execute(
            select(func.count()).where(
                UserClanRole.clan_id == clan_id,
                UserClanRole.is_approved.is_(True),
            )
        )
        pending_users_result = await self._session.execute(
            select(func.count()).where(
                UserClanRole.clan_id == clan_id,
                UserClanRole.is_approved.is_(False),
            )
        )
        total_members_result = await self._session.execute(
            select(func.count()).where(ClanMembership.clan_id == clan_id)
        )

        return {
            "total_users": total_users_result.scalar() or 0,
            "approved_users": approved_users_result.scalar() or 0,
            "pending_users": pending_users_result.scalar() or 0,
            "total_members": total_members_result.scalar() or 0,
        }

    async def get_clan_for_update(self, clan_id: uuid.UUID) -> ClanEntity | None:
        model = await self._session.get(Clan, clan_id)
        return to_domain(model) if model else None

    async def save_clan(self, clan: ClanEntity) -> Clan | None:
        """Apply the mutated aggregate onto its (session-tracked) ORM row.

        Event collection is the handler's job (it holds the UoW and tracks the
        aggregate); this only maps state onto the ORM the session will flush.
        """
        model = await self._session.get(Clan, clan.id)
        if model is not None:
            apply_to_orm(clan, model)
        return model

    async def approve_user(self, ucr: UserClanRole, approved_by: uuid.UUID) -> None:
        ucr.is_approved = True
        ucr.approved_by = approved_by
        ucr.approved_at = datetime.now(UTC)

    async def delete_user_role(self, ucr: UserClanRole) -> None:
        await self._session.delete(ucr)

    async def change_role(self, ucr: UserClanRole, new_role: str) -> None:
        ucr.role = new_role

    async def get_membership_with_person(
        self, clan_id: uuid.UUID, person_id: uuid.UUID
    ) -> ClanMembership | None:
        result = await self._session.execute(
            select(ClanMembership)
            .join(Person, Person.id == ClanMembership.person_id)
            .where(
                ClanMembership.clan_id == clan_id,
                ClanMembership.person_id == person_id,
                Person.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_founder_membership(self, clan_id: uuid.UUID) -> ClanMembership | None:
        result = await self._session.execute(
            select(ClanMembership).where(
                ClanMembership.clan_id == clan_id, ClanMembership.is_founder.is_(True)
            )
        )
        return result.scalars().first()

    async def swap_founder(self, clan_id: uuid.UUID, target_membership_id: uuid.UUID) -> None:
        """Clear-then-set in two ORDERED statements (session.execute emits SQL
        immediately, unlike ORM attribute flushes whose order is unspecified) —
        required because uq_clan_memberships_one_founder is an immediate partial
        unique index (Postgres cannot defer a partial unique)."""
        await self._session.execute(
            update(ClanMembership)
            .where(ClanMembership.clan_id == clan_id, ClanMembership.is_founder.is_(True))
            .values(is_founder=False)
        )
        await self._session.execute(
            update(ClanMembership)
            .where(ClanMembership.id == target_membership_id)
            .values(is_founder=True)
        )
