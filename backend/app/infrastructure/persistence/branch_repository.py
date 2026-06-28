"""SQLAlchemy implementation of BranchRepository.

Encapsulates all Branch persistence logic including parent-branch
validation and ordered listing.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.domain.branch.entity import Branch as BranchEntity
from app.infrastructure.persistence.branch_mapper import apply_to_orm, to_domain, to_orm
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.models.branch import Branch as BranchModel
from app.models.clan_membership import ClanMembership


class SqlAlchemyBranchRepository:
    """Concrete Branch repository backed by SQLAlchemy + PostgreSQL."""

    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow
        self._session = uow.session

    async def get_by_id(self, branch_id: uuid.UUID, clan_id: uuid.UUID) -> BranchEntity | None:
        result = await self._session.execute(
            select(BranchModel).where(BranchModel.id == branch_id, BranchModel.clan_id == clan_id)
        )
        model = result.scalar_one_or_none()
        return to_domain(model) if model else None

    async def person_in_clan(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(ClanMembership.person_id).where(
                ClanMembership.person_id == person_id,
                ClanMembership.clan_id == clan_id,
            )
        )
        return result.first() is not None

    async def list_in_clan(self, clan_id: uuid.UUID) -> list[BranchEntity]:
        result = await self._session.execute(
            select(BranchModel)
            .where(BranchModel.clan_id == clan_id)
            .order_by(BranchModel.branch_order.asc().nullslast(), BranchModel.name.asc())
        )
        return [to_domain(m) for m in result.scalars().all()]

    async def save(self, branch: BranchEntity) -> None:
        """Insert or update a Branch."""
        self._uow.track(branch)
        existing = await self._session.execute(
            select(BranchModel).where(BranchModel.id == branch.id)
        )
        model = existing.scalar_one_or_none()
        if model:
            apply_to_orm(branch, model)
        else:
            self._session.add(to_orm(branch))

    async def delete(self, branch: BranchEntity) -> None:
        """Hard-delete a branch."""
        self._uow.track(branch)
        result = await self._session.execute(select(BranchModel).where(BranchModel.id == branch.id))
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
