"""SQLAlchemy implementation of ClanRepository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
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

    async def approve_if_pending(self, ucr_id: uuid.UUID, approved_by: uuid.UUID) -> bool:
        """Atomically flip a STILL-PENDING role to approved; return whether it won.

        A single conditional UPDATE (``WHERE id = :id AND is_approved = false``)
        is the race guard for two admins working the same pending row: it either
        matches the pending row (True) or matches nothing (False) because a
        concurrent approve already approved it or a concurrent reject/remove
        deleted it. Unlike a read-then-ORM-mutate, a lost race here can never emit
        a 0-row ORM UPDATE (``StaleDataError`` -> raw 500); the caller resolves the
        loss to a precise 4xx instead. Mirrors the invitation ``transition_status``
        guard, including ``synchronize_session=False`` (the caller does not trust
        the pre-read ORM instance's attributes after this write)."""
        result = await self._session.execute(
            update(UserClanRole)
            .where(UserClanRole.id == ucr_id, UserClanRole.is_approved.is_(False))
            .values(is_approved=True, approved_by=approved_by, approved_at=datetime.now(UTC))
            .returning(UserClanRole.id)
            .execution_options(synchronize_session=False)
        )
        return result.scalar_one_or_none() is not None

    async def role_is_approved(self, ucr_id: uuid.UUID) -> bool | None:
        """Truthful current approval state of a role BY ID: None if the row is
        gone, else its ``is_approved``.

        Selects the *column* (not the entity) so it bypasses the session identity
        map — after ``approve_if_pending`` the pre-read ORM instance still carries
        its stale ``is_approved=False``, so entity re-reads would lie. Keyed on the
        exact ``ucr_id`` the conditional write targeted (not the natural key), so a
        concurrent reject-then-re-invite that inserts a *fresh* pending row for the
        same user cannot be mistaken for 'this row was approved'."""
        result = await self._session.execute(
            select(UserClanRole.is_approved).where(UserClanRole.id == ucr_id)
        )
        return result.scalar_one_or_none()

    async def delete_role_by_id(self, ucr_id: uuid.UUID) -> bool:
        """Atomically delete a role BY ID (any state); return whether it won.

        remove_user's race guard: a conditional DELETE (``WHERE id = :id``) matches
        the row (True) or nothing (False) if a concurrent remove/reject already
        deleted it. Unlike ``session.delete`` + flush — whose 0-row DELETE does not
        raise, so remove would *silently succeed* on an already-gone row and write a
        phantom audit — this reports the loss so the caller raises a clean 404.
        ``synchronize_session=False``: the caller does not reuse the pre-read ORM
        instance after this write."""
        result = await self._session.execute(
            delete(UserClanRole)
            .where(UserClanRole.id == ucr_id)
            .returning(UserClanRole.id)
            .execution_options(synchronize_session=False)
        )
        return result.scalar_one_or_none() is not None

    async def delete_if_pending(self, ucr_id: uuid.UUID) -> bool:
        """Atomically delete a STILL-PENDING role; return whether it won.

        Reject's race guard, symmetric to ``approve_if_pending``: a conditional
        DELETE (``WHERE id = :id AND is_approved = false``) matches the pending
        row (True) or nothing (False) if a concurrent approve promoted it or a
        concurrent reject already deleted it — so reject can never delete an
        already-approved member out from under an approve, and never emits a
        0-row ORM DELETE."""
        result = await self._session.execute(
            delete(UserClanRole)
            .where(UserClanRole.id == ucr_id, UserClanRole.is_approved.is_(False))
            .returning(UserClanRole.id)
            .execution_options(synchronize_session=False)
        )
        return result.scalar_one_or_none() is not None

    async def change_role_if(self, ucr_id: uuid.UUID, expected_role: str, new_role: str) -> bool:
        """Atomically change a role BY ID with a compare-and-set on the role we read;
        return whether it won.

        change_role's race guard: ``UPDATE role = :new WHERE id = :id AND
        role = :expected``. Matches (True) only if the row still holds the role the
        caller based its decision on — so a concurrent change_role (lost update / dup
        audit) or a concurrent remove (0-row ORM UPDATE -> StaleDataError -> 500) both
        turn into a clean 0-row False that the caller resolves to a precise 4xx.
        ``synchronize_session=False`` (the pre-read ORM instance is not reused)."""
        result = await self._session.execute(
            update(UserClanRole)
            .where(UserClanRole.id == ucr_id, UserClanRole.role == expected_role)
            .values(role=new_role)
            .returning(UserClanRole.id)
            .execution_options(synchronize_session=False)
        )
        return result.scalar_one_or_none() is not None

    async def role_of(self, ucr_id: uuid.UUID) -> str | None:
        """Truthful current role of a membership BY ID (None if the row is gone).

        Column select (not entity) so it bypasses the identity map — the pre-read ORM
        instance carries the stale pre-write role — and keyed on the exact ``ucr_id``,
        so the loser can distinguish 'row deleted' (404) from 'role changed under me'
        (409) after a lost ``change_role_if``."""
        result = await self._session.execute(
            select(UserClanRole.role).where(UserClanRole.id == ucr_id)
        )
        return result.scalar_one_or_none()

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

    async def swap_founder(
        self, clan_id: uuid.UUID, target_membership_id: uuid.UUID
    ) -> uuid.UUID | None:
        """Clear-then-set in two ORDERED statements (session.execute emits SQL
        immediately, unlike ORM attribute flushes whose order is unspecified) —
        required because uq_clan_memberships_one_founder is an immediate partial
        unique index (Postgres cannot defer a partial unique). The CLEAR statement
        RETURNING person_id reports the founder actually cleared by this
        statement, so the caller's previous_person_id reflects the row this swap
        itself displaced rather than a separately-read snapshot."""
        clear_result = await self._session.execute(
            update(ClanMembership)
            .where(ClanMembership.clan_id == clan_id, ClanMembership.is_founder.is_(True))
            .values(is_founder=False)
            .returning(ClanMembership.person_id)
        )
        previous_person_id = clear_result.scalar_one_or_none()
        await self._session.execute(
            update(ClanMembership)
            .where(ClanMembership.id == target_membership_id)
            .values(is_founder=True)
        )
        return previous_person_id
