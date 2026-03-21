"""Branches API routes — thin controller delegating to Branch handlers."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.branch.handlers import BranchCommandHandler, BranchQueryHandler
from app.core.database import get_db
from app.core.permissions import ClanRole, RequireAdmin, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.value_objects import ActorInfo
from app.schemas.branch import BranchCreateRequest, BranchUpdateRequest

router = APIRouter()


def _make_handlers(db: AsyncSession) -> tuple[BranchCommandHandler, BranchQueryHandler]:
    from app.infrastructure.event_dispatcher import create_event_dispatcher
    from app.infrastructure.persistence.branch_repository import SqlAlchemyBranchRepository
    from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

    repo = SqlAlchemyBranchRepository(db)
    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    return BranchCommandHandler(repo, uow), BranchQueryHandler(repo)


@router.get("")
async def list_branches(
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """List all branches for the current clan."""
    _, query_handler = _make_handlers(db)
    branches = await query_handler.list_branches(clan_id=clan_id)
    return {"data": [b.model_dump() for b in branches]}


@router.post("", status_code=201)
async def create_branch(
    body: BranchCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a new branch."""
    cmd_handler, _ = _make_handlers(db)
    branch = await cmd_handler.create(
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, "editor"),
        name=body.name,
        description=body.description,
        founder_person_id=body.founder_person_id,
        parent_branch_id=body.parent_branch_id,
        branch_order=body.branch_order,
    )
    return {"data": branch.model_dump()}


@router.get("/{branch_id}")
async def get_branch(
    branch_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get a single branch by ID."""
    _, query_handler = _make_handlers(db)
    branch = await query_handler.get(branch_id=branch_id, clan_id=clan_id)
    return {"data": branch.model_dump()}


@router.patch("/{branch_id}")
async def update_branch(
    branch_id: uuid.UUID,
    body: BranchUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Update a branch."""
    cmd_handler, _ = _make_handlers(db)
    branch = await cmd_handler.update(
        branch_id=branch_id,
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, "editor"),
        changes=body.model_dump(exclude_unset=True),
    )
    return {"data": branch.model_dump()}


@router.delete("/{branch_id}")
async def delete_branch(
    branch_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Delete a branch (admin only)."""
    cmd_handler, _ = _make_handlers(db)
    await cmd_handler.delete(
        branch_id=branch_id,
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, "admin"),
    )
    return {"data": {"message": "Branch deleted", "id": str(branch_id)}}
