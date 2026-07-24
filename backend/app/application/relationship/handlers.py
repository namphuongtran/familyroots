"""Relationship use-case handlers.

Orchestrate domain entities, repository, validator, and UoW.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, cast

from app.application.relationship.commands import (
    CreateMarriage,
    CreateParentChild,
    DeleteMarriage,
    DeleteParentChild,
    UpdateMarriage,
    UpdateParentChild,
)
from app.domain.relationship.entities import Marriage, ParentChild
from app.domain.relationship.repository import MarriageRepository, ParentChildRepository
from app.domain.relationship.validator import RelationshipDomainValidator
from app.domain.shared.exceptions import EntityNotFoundError, ValidationError
from app.domain.shared.unit_of_work import UnitOfWork
from app.schemas.marriage import MarriageResponse
from app.schemas.parent_child import ParentChildResponse


class MarriageCommandHandler:
    def __init__(
        self,
        repo: MarriageRepository,
        uow: UnitOfWork,
        validator: RelationshipDomainValidator,
    ) -> None:
        self._repo = repo
        self._uow = uow
        self._validator = validator

    async def create(self, cmd: CreateMarriage) -> MarriageResponse:
        await self._validator.ensure_persons_in_clan([cmd.person1_id, cmd.person2_id], cmd.clan_id)
        await self._validator.check_duplicate_marriage(cmd.person1_id, cmd.person2_id, cmd.clan_id)
        if cmd.status != "divorced":
            await self._validator.check_spouse_order(
                cmd.person1_id, cmd.person2_id, cmd.spouse_order, cmd.clan_id
            )

        marriage = Marriage.create(
            person1_id=cmd.person1_id,
            person2_id=cmd.person2_id,
            clan_id=cmd.clan_id,
            actor=cmd.actor,
            marriage_date=cmd.marriage_date,
            marriage_date_precision=cmd.marriage_date_precision,
            marriage_date_display=cmd.marriage_date_display,
            divorce_date=cmd.divorce_date,
            divorce_date_precision=cmd.divorce_date_precision,
            divorce_date_display=cmd.divorce_date_display,
            marriage_place=cmd.marriage_place,
            status=cmd.status,
            spouse_order=cmd.spouse_order,
            notes=cmd.notes,
        )
        await self._repo.save(marriage)
        await self._uow.commit()
        return MarriageResponse.model_validate(marriage)

    async def update(self, cmd: UpdateMarriage) -> MarriageResponse:
        marriage = await self._repo.get_by_id(cmd.marriage_id, cmd.clan_id)
        if not marriage:
            raise EntityNotFoundError("marriage_not_found")

        # H2: re-validate create-time rules before applying an update — a PATCH
        # must not be able to bypass what CREATE would have blocked.
        new_status = cast(str, cmd.changes.get("status", marriage.status))
        new_order = cast("int | None", cmd.changes.get("spouse_order", marriage.spouse_order))
        # Re-check duplicate_marriage only when the pair transitions from divorced
        # to any active (non-divorced) status — has_active_marriage already
        # excludes divorced rows, so a flip between two non-divorced statuses
        # (e.g. married -> widowed) can't newly create an active-marriage clash.
        if "status" in cmd.changes and new_status != "divorced" and marriage.status == "divorced":
            await self._validator.check_duplicate_marriage(
                marriage.person1_id,
                marriage.person2_id,
                cmd.clan_id,
                exclude_marriage_id=marriage.id,
            )
        if new_status != "divorced" and ("spouse_order" in cmd.changes or "status" in cmd.changes):
            await self._validator.check_spouse_order(
                marriage.person1_id,
                marriage.person2_id,
                new_order,
                cmd.clan_id,
                exclude_marriage_id=marriage.id,
            )

        # M1: a PATCH must not be able to put the marriage into a
        # divorce-before-marriage state that CREATE would have rejected. Runs
        # BEFORE marriage.update()/repo.save() — the DB also refuses this via
        # the marriages_divorce_after_marriage CHECK constraint, but that
        # CheckViolation is unmapped and would surface as a raw 500; this
        # pre-write check raises a clean domain 422 instead.
        eff_marriage = cast("date | None", cmd.changes.get("marriage_date", marriage.marriage_date))
        eff_divorce = cast("date | None", cmd.changes.get("divorce_date", marriage.divorce_date))
        if eff_marriage and eff_divorce and eff_divorce < eff_marriage:
            raise ValidationError("relationship.divorce_before_marriage")

        marriage.update(cmd.changes, cmd.actor, cmd.clan_id)
        await self._repo.save(marriage, expected_version=cmd.expected_version)
        await self._uow.commit()
        return MarriageResponse.model_validate(marriage)

    async def delete(self, cmd: DeleteMarriage) -> None:
        marriage = await self._repo.get_by_id(cmd.marriage_id, cmd.clan_id)
        if not marriage:
            raise EntityNotFoundError("marriage_not_found")

        marriage.soft_delete(cmd.actor, cmd.clan_id)
        await self._repo.save(marriage)
        await self._uow.commit()


class ParentChildCommandHandler:
    def __init__(
        self,
        repo: ParentChildRepository,
        uow: UnitOfWork,
        validator: RelationshipDomainValidator,
    ) -> None:
        self._repo = repo
        self._uow = uow
        self._validator = validator

    async def create(
        self, cmd: CreateParentChild
    ) -> tuple[ParentChildResponse, dict[str, Any] | None]:
        """Create parent-child link. Returns (link, optional warning dict)."""
        await self._validator.ensure_persons_in_clan([cmd.parent_id, cmd.child_id], cmd.clan_id)
        await self._validator.check_duplicate_parent_child(cmd.parent_id, cmd.child_id, cmd.clan_id)
        warning = await self._validator.validate_parent_child(
            cmd.parent_id, cmd.child_id, cmd.relationship_type, cmd.clan_id
        )

        link = ParentChild.create(
            parent_id=cmd.parent_id,
            child_id=cmd.child_id,
            clan_id=cmd.clan_id,
            actor=cmd.actor,
            relationship_type=cmd.relationship_type,
            birth_order=cmd.birth_order,
            notes=cmd.notes,
        )
        await self._repo.save(link)
        await self._uow.commit()
        return ParentChildResponse.model_validate(link), warning

    async def update(self, cmd: UpdateParentChild) -> ParentChildResponse:
        link = await self._repo.get_by_id(cmd.link_id, cmd.clan_id)
        if not link:
            raise EntityNotFoundError("parent_child_not_found")

        # H2: re-validate create-time rules before applying a relationship_type
        # change — e.g. adopted -> biological must still respect the bio-parent
        # limit and the minimum parent/child age gap.
        new_type = cast(str, cmd.changes.get("relationship_type", link.relationship_type))
        if new_type != link.relationship_type:
            # Same rules as create; exclude this edge from the bio count; cycle
            # check skipped — parent/child ids are immutable on update.
            await self._validator.validate_parent_child(
                link.parent_id,
                link.child_id,
                new_type,
                cmd.clan_id,
                exclude_link_id=link.id,
                check_cycle=False,
            )

        link.update(cmd.changes, cmd.actor, cmd.clan_id)
        await self._repo.save(link, expected_version=cmd.expected_version)
        await self._uow.commit()
        return ParentChildResponse.model_validate(link)

    async def delete(self, cmd: DeleteParentChild) -> None:
        link = await self._repo.get_by_id(cmd.link_id, cmd.clan_id)
        if not link:
            raise EntityNotFoundError("parent_child_not_found")

        link.soft_delete(cmd.actor, cmd.clan_id)
        await self._repo.save(link)
        await self._uow.commit()


class MarriageQueryHandler:
    def __init__(self, repo: MarriageRepository) -> None:
        self._repo = repo

    async def get_by_id(self, marriage_id: uuid.UUID, clan_id: uuid.UUID) -> Marriage | None:
        return await self._repo.get_by_id(marriage_id, clan_id)


class ParentChildQueryHandler:
    def __init__(self, repo: ParentChildRepository) -> None:
        self._repo = repo

    async def get_by_id(self, link_id: uuid.UUID, clan_id: uuid.UUID) -> ParentChild | None:
        return await self._repo.get_by_id(link_id, clan_id)
