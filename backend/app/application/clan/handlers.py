"""Clan use-case handlers.

Orchestrate clan management operations with domain events
for automatic audit logging.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.application.clan.commands import (
    ApproveUser,
    ChangeUserRole,
    DesignateFounder,
    RejectUser,
    RemoveUser,
    UpdateClan,
)
from app.domain.clan.events import (
    FounderDesignated,
    UserApproved,
    UserRejected,
    UserRemoved,
    UserRoleChanged,
)
from app.domain.clan.repository import ClanRepository
from app.domain.shared.entity import AggregateRoot
from app.domain.shared.exceptions import (
    BusinessRuleViolation,
    ConflictError,
    EntityNotFoundError,
    ForbiddenError,
)
from app.domain.shared.unit_of_work import UnitOfWork


class ClanCommandHandler:
    """Handles Clan write operations."""

    def __init__(self, repo: ClanRepository, uow: UnitOfWork) -> None:
        self._repo = repo
        self._uow = uow

    async def update_clan(self, cmd: UpdateClan) -> Any:
        """Update clan info through the Clan aggregate (whitelist + audit event)."""
        clan = await self._repo.get_clan_for_update(cmd.clan_id)
        if clan is None:
            raise EntityNotFoundError("clan_not_found")

        clan.update(cmd.changes, cmd.actor)  # enforces the updatable-field whitelist
        self._uow.track(clan)  # UoW harvests the ClanUpdated event on commit
        result = await self._repo.save_clan(clan)
        await self._uow.commit()
        return result

    async def approve_user(self, cmd: ApproveUser) -> None:
        """Approve a pending user."""
        ucr = await self._repo.get_user_clan_role(cmd.clan_id, cmd.target_user_id)
        if not ucr:
            raise EntityNotFoundError("user_not_found")
        if ucr.is_approved:
            raise ConflictError("user.already_approved")

        await self._repo.approve_user(ucr, cmd.actor.user_id)

        agg = AggregateRoot()
        agg.add_event(
            UserApproved(
                clan_id=cmd.clan_id,
                actor_id=cmd.actor.user_id,
                actor_role=cmd.actor.role,
                resource_id=ucr.id,
                target_user_id=cmd.target_user_id,
            )
        )
        self._uow.track(agg)
        await self._uow.commit()

    async def reject_user(self, cmd: RejectUser) -> None:
        """Reject (delete) a pending user."""
        ucr = await self._repo.get_user_clan_role(cmd.clan_id, cmd.target_user_id)
        if not ucr:
            raise EntityNotFoundError("user_not_found")
        if ucr.is_approved:
            raise EntityNotFoundError("user_not_found")

        await self._repo.delete_user_role(ucr)

        agg = AggregateRoot()
        agg.add_event(
            UserRejected(
                clan_id=cmd.clan_id,
                actor_id=cmd.actor.user_id,
                actor_role=cmd.actor.role,
                resource_id=ucr.id,
                target_user_id=cmd.target_user_id,
            )
        )
        self._uow.track(agg)
        await self._uow.commit()

    async def change_role(self, cmd: ChangeUserRole) -> None:
        """Change a user's role with last-admin protection."""
        if cmd.new_role not in ("admin", "editor", "viewer"):
            raise BusinessRuleViolation(
                "invalid_role",
                detail={"allowed": ["admin", "editor", "viewer"]},
            )

        ucr = await self._repo.get_user_clan_role(cmd.clan_id, cmd.target_user_id)
        if not ucr:
            raise EntityNotFoundError("user_not_found")

        # Invariant: a clan always keeps >= 1 approved admin (any target, not
        # just self-demotion). lock_admin_count takes FOR UPDATE row locks so
        # concurrent demotions serialize instead of both passing the count.
        if ucr.role == "admin" and cmd.new_role != "admin":
            admin_count = await self._repo.lock_admin_count(cmd.clan_id)
            if admin_count <= 1:
                raise ForbiddenError("clan.last_admin_cannot_demote")

        old_role = ucr.role
        await self._repo.change_role(ucr, cmd.new_role)

        agg = AggregateRoot()
        agg.add_event(
            UserRoleChanged(
                clan_id=cmd.clan_id,
                actor_id=cmd.actor.user_id,
                actor_role=cmd.actor.role,
                resource_id=ucr.id,
                target_user_id=cmd.target_user_id,
                old_role=old_role,
                new_role=cmd.new_role,
            )
        )
        self._uow.track(agg)
        await self._uow.commit()

    async def remove_user(self, cmd: RemoveUser) -> None:
        """Remove a user from the clan."""
        if cmd.target_user_id == cmd.actor.user_id:
            raise ForbiddenError("clan.cannot_remove_self")

        ucr = await self._repo.get_user_clan_role(cmd.clan_id, cmd.target_user_id)
        if not ucr:
            raise EntityNotFoundError("user_not_found")

        if ucr.role == "admin":
            admin_count = await self._repo.lock_admin_count(cmd.clan_id)
            if admin_count <= 1:
                raise ForbiddenError("clan.last_admin_cannot_remove")

        await self._repo.delete_user_role(ucr)

        agg = AggregateRoot()
        agg.add_event(
            UserRemoved(
                clan_id=cmd.clan_id,
                actor_id=cmd.actor.user_id,
                actor_role=cmd.actor.role,
                resource_id=ucr.id,
                target_user_id=cmd.target_user_id,
            )
        )
        self._uow.track(agg)
        await self._uow.commit()

    async def designate_founder(self, cmd: DesignateFounder) -> dict[str, Any]:
        """Designate or correct the clan's thủy tổ (ADR-026: exactly one live founder).

        Idempotent: re-designating the current founder writes nothing and reports
        previous == person_id (from the pre-read, which is what decides idempotent
        vs. swap in the first place — no swap runs, so there is nothing for a
        RETURNING clause to report). Swap is clear-then-set as two explicitly
        ORDERED statements (``repo.swap_founder``), not two ORM attribute mutations
        left to the UoW's single flush — SQLAlchemy does not guarantee dirty-object
        flush order, so an attribute-mutation swap could emit the SET before the
        CLEAR and spuriously trip the 023 partial unique index within this same
        transaction. The 023 index still backstops genuine out-of-band writers
        (23505 → 409). In the swap branch, ``previous_person_id`` comes from
        ``swap_founder``'s own ``RETURNING`` — the founder the CLEAR statement
        actually displaced — rather than the pre-read snapshot, so it stays
        truthful even if another writer changed the founder between the pre-read
        and this statement.
        """
        target = await self._repo.get_membership_with_person(cmd.clan_id, cmd.person_id)
        if target is None:
            raise EntityNotFoundError("person_not_found")

        current = await self._repo.get_founder_membership(cmd.clan_id)
        # Decides idempotent-vs-swap only; the swap branch below overrides
        # previous_person_id with the RETURNING result from swap_founder.
        previous_person_id = current.person_id if current else None
        if current is None or current.person_id != cmd.person_id:
            previous_person_id = await self._repo.swap_founder(cmd.clan_id, target.id)

        agg = AggregateRoot()
        agg.add_event(
            FounderDesignated(
                clan_id=cmd.clan_id,
                actor_id=cmd.actor.user_id,
                actor_role=cmd.actor.role,
                resource_id=target.id,
                person_id=cmd.person_id,
                previous_person_id=previous_person_id,
            )
        )
        self._uow.track(agg)
        await self._uow.commit()
        return {"person_id": cmd.person_id, "previous_person_id": previous_person_id}


class ClanQueryHandler:
    """Handles Clan read operations."""

    def __init__(self, repo: ClanRepository) -> None:
        self._repo = repo

    async def get_clan(self, clan_id: uuid.UUID) -> Any:
        return await self._repo.get_clan(clan_id)

    async def list_users(
        self, clan_id: uuid.UUID, approved: bool, cursor: str | None, limit: int
    ) -> dict[str, Any]:
        return await self._repo.list_users(clan_id, approved, cursor, limit)

    async def get_clan_stats(self, clan_id: uuid.UUID) -> dict[str, int]:
        """Get aggregate stats for clan dashboards."""
        return await self._repo.get_clan_stats(clan_id)
