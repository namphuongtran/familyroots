"""Relationship use-case handlers.

Orchestrate domain entities, repository, validator, and UoW.
"""

from __future__ import annotations

import uuid
from typing import Any

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
from app.domain.shared.exceptions import EntityNotFoundError
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.schemas.marriage import MarriageResponse
from app.schemas.parent_child import ParentChildResponse


class MarriageCommandHandler:
    def __init__(
        self,
        repo: MarriageRepository,
        uow: SqlAlchemyUnitOfWork,
        validator: RelationshipDomainValidator,
    ) -> None:
        self._repo = repo
        self._uow = uow
        self._validator = validator

    async def create(self, cmd: CreateMarriage) -> MarriageResponse:
        await self._validator.ensure_persons_in_clan([cmd.person1_id, cmd.person2_id], cmd.clan_id)
        await self._validator.check_duplicate_marriage(cmd.person1_id, cmd.person2_id)

        marriage = Marriage.create(
            person1_id=cmd.person1_id,
            person2_id=cmd.person2_id,
            clan_id=cmd.clan_id,
            actor=cmd.actor,
            marriage_date=cmd.marriage_date,
            divorce_date=cmd.divorce_date,
            marriage_place=cmd.marriage_place,
            status=cmd.status,
            spouse_order=cmd.spouse_order,
            notes=cmd.notes,
        )
        self._uow.track(marriage)
        await self._repo.save(marriage)
        await self._uow.commit()
        return MarriageResponse.model_validate(marriage)

    async def update(self, cmd: UpdateMarriage) -> MarriageResponse:
        marriage = await self._repo.get_by_id(cmd.marriage_id, cmd.clan_id)
        if not marriage:
            raise EntityNotFoundError("marriage_not_found")

        marriage.update(cmd.changes, cmd.actor, cmd.clan_id)
        self._uow.track(marriage)
        await self._repo.save(marriage)
        await self._uow.commit()
        return MarriageResponse.model_validate(marriage)

    async def delete(self, cmd: DeleteMarriage) -> None:
        marriage = await self._repo.get_by_id(cmd.marriage_id, cmd.clan_id)
        if not marriage:
            raise EntityNotFoundError("marriage_not_found")

        marriage.soft_delete(cmd.actor, cmd.clan_id)
        self._uow.track(marriage)
        await self._repo.save(marriage)
        await self._uow.commit()


class ParentChildCommandHandler:
    def __init__(
        self,
        repo: ParentChildRepository,
        uow: SqlAlchemyUnitOfWork,
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
        await self._validator.check_duplicate_parent_child(cmd.parent_id, cmd.child_id)
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
        self._uow.track(link)
        await self._repo.save(link)
        await self._uow.commit()
        return ParentChildResponse.model_validate(link), warning

    async def update(self, cmd: UpdateParentChild) -> ParentChildResponse:
        link = await self._repo.get_by_id(cmd.link_id, cmd.clan_id)
        if not link:
            raise EntityNotFoundError("parent_child_not_found")

        link.update(cmd.changes, cmd.actor, cmd.clan_id)
        self._uow.track(link)
        await self._repo.save(link)
        await self._uow.commit()
        return ParentChildResponse.model_validate(link)

    async def delete(self, cmd: DeleteParentChild) -> None:
        link = await self._repo.get_by_id(cmd.link_id, cmd.clan_id)
        if not link:
            raise EntityNotFoundError("parent_child_not_found")

        link.soft_delete(cmd.actor, cmd.clan_id)
        self._uow.track(link)
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
