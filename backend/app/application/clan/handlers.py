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
        if result is not None:
            # The UPDATE bumps the server-side `updated_at` (onupdate=func.now(),
            # app/models/base.py:34-39), a SQL expression SQLAlchemy cannot evaluate
            # client-side. `eager_defaults="auto"` (the 2.0 default) uses RETURNING for
            # INSERT only, never for UPDATE, so that attribute is left unloaded and the
            # caller's `ClanResponse.model_validate(...)` starts a lazy load with no
            # greenlet to run the IO in -> MissingGreenlet -> 500, with the row already
            # written. Re-fetch the timestamps inside the async context; the targeted
            # attribute list keeps Clan's four `lazy="selectin"` relationships loaded
            # instead of re-running four SELECTs. Same remedy, same reason, as
            # app/application/person/claim_handlers.py:186,227.
            # A no-op PATCH expires nothing and never had the bug; the extra read is
            # harmless there. Pinned by
            # tests/integration/test_clan_patch_returns_updated_row.py.
            await self._uow.session.refresh(result, attribute_names=["updated_at", "created_at"])
        return result

    async def approve_user(self, cmd: ApproveUser) -> None:
        """Approve a pending user."""
        ucr = await self._repo.get_user_clan_role(cmd.clan_id, cmd.target_user_id)
        if not ucr:
            raise EntityNotFoundError("user_not_found")
        if ucr.is_approved:
            raise ConflictError("user.already_approved")

        # Atomic guard: flip the row only while it is still pending. A concurrent
        # reject/remove (delete) or a concurrent approve can land between the read
        # above and here; the conditional UPDATE wins on exactly one of them and
        # returns False on the loser — which we resolve to a precise 4xx below,
        # never a 0-row ORM UPDATE (StaleDataError -> 500) and never a duplicate
        # UserApproved audit row.
        if not await self._repo.approve_if_pending(ucr.id, cmd.actor.user_id):
            # Lost the race on THIS row: it was either deleted (reject/remove won)
            # or approved (a concurrent approve won) — it cannot still be pending,
            # or the conditional UPDATE would have matched. Resolve by the exact
            # row id (a concurrent re-invite inserts a *different* pending row that
            # must not be read as "this one was approved").
            approved = await self._repo.role_is_approved(ucr.id)
            if approved is None:
                raise EntityNotFoundError("user_not_found")
            raise ConflictError("user.already_approved")

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

        # Atomic guard (symmetric to approve): delete only while still pending, so a
        # concurrent approve that committed first is not silently removed here — the
        # conditional DELETE matches nothing and reject reports user_not_found.
        if not await self._repo.delete_if_pending(ucr.id):
            raise EntityNotFoundError("user_not_found")

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
        # Atomic guard: compare-and-set on the role we read. A concurrent change_role
        # (lost update + duplicate audit) or a concurrent remove/reject (0-row ORM
        # UPDATE -> StaleDataError -> 500) both turn into a clean 0-row loss here,
        # resolved by the exact row id: gone -> 404, role moved under us -> 409.
        if not await self._repo.change_role_if(ucr.id, old_role, cmd.new_role):
            if await self._repo.role_of(ucr.id) is None:
                raise EntityNotFoundError("user_not_found")
            raise ConflictError("clan.role_changed_concurrently")

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

        # Atomic guard: a conditional DELETE reports whether it won. A concurrent
        # remove/reject that deleted the row first would otherwise make the ORM's
        # 0-row DELETE silently succeed and write a phantom audit; here the loser
        # gets a clean 404 and emits nothing.
        if not await self._repo.delete_role_by_id(ucr.id):
            raise EntityNotFoundError("user_not_found")

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
