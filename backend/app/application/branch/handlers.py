"""Branch use-case handlers.

Orchestrate branch CRUD through domain entities and repository protocol.
No SQLAlchemy imports — fully DIP-compliant.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.domain.branch.entity import Branch
from app.domain.branch.repository import BranchRepository
from app.domain.shared.exceptions import EntityNotFoundError
from app.domain.shared.unit_of_work import UnitOfWork
from app.domain.shared.value_objects import ActorInfo
from app.schemas.branch import BranchResponse


class BranchCommandHandler:
    """Handles branch write operations."""

    def __init__(self, repo: BranchRepository, uow: UnitOfWork) -> None:
        self._repo = repo
        self._uow = uow

    async def create(
        self,
        *,
        clan_id: uuid.UUID,
        actor: ActorInfo,
        name: str,
        description: str | None = None,
        founder_person_id: uuid.UUID | None = None,
        parent_branch_id: uuid.UUID | None = None,
        branch_order: int | None = None,
    ) -> BranchResponse:
        # Validate parent branch exists
        if parent_branch_id:
            parent = await self._repo.get_by_id(parent_branch_id, clan_id)
            if not parent:
                raise EntityNotFoundError("branch_not_found", {"branch_id": str(parent_branch_id)})

        branch = Branch.create(
            clan_id=clan_id,
            name=name,
            actor=actor,
            description=description,
            founder_person_id=founder_person_id,
            parent_branch_id=parent_branch_id,
            branch_order=branch_order,
        )
        await self._repo.save(branch)
        await self._uow.commit()

        return BranchResponse(
            id=branch.id,
            clan_id=branch.clan_id,
            name=branch.name,
            description=branch.description,
            founder_person_id=branch.founder_person_id,
            parent_branch_id=branch.parent_branch_id,
            branch_order=branch.branch_order,
            created_at=branch.created_at,
            updated_at=branch.updated_at,
        )

    async def update(
        self,
        *,
        branch_id: uuid.UUID,
        clan_id: uuid.UUID,
        actor: ActorInfo,
        changes: dict[str, Any],
    ) -> BranchResponse:
        branch = await self._get_or_raise(branch_id, clan_id)
        branch.update(changes, actor)
        await self._repo.save(branch)
        await self._uow.commit()

        return BranchResponse(
            id=branch.id,
            clan_id=branch.clan_id,
            name=branch.name,
            description=branch.description,
            founder_person_id=branch.founder_person_id,
            parent_branch_id=branch.parent_branch_id,
            branch_order=branch.branch_order,
            created_at=branch.created_at,
            updated_at=branch.updated_at,
        )

    async def delete(
        self,
        *,
        branch_id: uuid.UUID,
        clan_id: uuid.UUID,
        actor: ActorInfo,
    ) -> None:
        branch = await self._get_or_raise(branch_id, clan_id)
        branch.delete(actor)
        await self._repo.delete(branch)
        await self._uow.commit()

    async def _get_or_raise(self, branch_id: uuid.UUID, clan_id: uuid.UUID) -> Branch:
        branch = await self._repo.get_by_id(branch_id, clan_id)
        if not branch:
            raise EntityNotFoundError("branch_not_found")
        return branch


class BranchQueryHandler:
    """Read-only handler for branch queries."""

    def __init__(self, repo: BranchRepository) -> None:
        self._repo = repo

    async def get(self, *, branch_id: uuid.UUID, clan_id: uuid.UUID) -> BranchResponse:
        branch = await self._repo.get_by_id(branch_id, clan_id)
        if not branch:
            raise EntityNotFoundError("branch_not_found")
        return BranchResponse(
            id=branch.id,
            clan_id=branch.clan_id,
            name=branch.name,
            description=branch.description,
            founder_person_id=branch.founder_person_id,
            parent_branch_id=branch.parent_branch_id,
            branch_order=branch.branch_order,
            created_at=branch.created_at,
            updated_at=branch.updated_at,
        )

    async def list_branches(self, *, clan_id: uuid.UUID) -> list[BranchResponse]:
        branches = await self._repo.list_in_clan(clan_id)
        return [
            BranchResponse(
                id=b.id,
                clan_id=b.clan_id,
                name=b.name,
                description=b.description,
                founder_person_id=b.founder_person_id,
                parent_branch_id=b.parent_branch_id,
                branch_order=b.branch_order,
                created_at=b.created_at,
                updated_at=b.updated_at,
            )
            for b in branches
        ]
