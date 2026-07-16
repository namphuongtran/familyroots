"""Branches API routes — thin controller delegating to Branch handlers."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.application.branch.handlers import BranchCommandHandler, BranchQueryHandler
from app.core.permissions import ClanRole, RequireAdmin, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.dependencies import get_branch_command_handler, get_branch_query_handler
from app.schemas.branch import BranchCreateRequest, BranchResponse, BranchUpdateRequest
from app.schemas.envelope import created, ok, ok_list, ok_message
from app.services.translator import t

router = APIRouter()


@router.get("", responses=ok_list(BranchResponse))
async def list_branches(
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: BranchQueryHandler = Depends(get_branch_query_handler),
    role: ClanRole = RequireViewer,
    fields: str | None = Query(None),
) -> dict[str, Any]:
    """List all branches for the current clan."""
    branches = await query_handler.list_branches(clan_id=clan_id)
    data = [b.model_dump() for b in branches]
    if fields:
        field_set = {f.strip() for f in fields.split(",")}
        data = [{k: v for k, v in d.items() if k in field_set} for d in data]
    return {"data": data}


@router.post("", status_code=201, responses=created(BranchResponse))
async def create_branch(
    body: BranchCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: BranchCommandHandler = Depends(get_branch_command_handler),
    role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a new branch."""
    branch = await cmd_handler.create(
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, role.value),
        name=body.name,
        description=body.description,
        founder_person_id=body.founder_person_id,
        parent_branch_id=body.parent_branch_id,
        branch_order=body.branch_order,
    )
    return {"data": branch.model_dump()}


@router.get("/{branch_id}", responses=ok(BranchResponse))
async def get_branch(
    branch_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: BranchQueryHandler = Depends(get_branch_query_handler),
    role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get a single branch by ID."""
    branch = await query_handler.get(branch_id=branch_id, clan_id=clan_id)
    return {"data": branch.model_dump()}


@router.patch("/{branch_id}", responses=ok(BranchResponse))
async def update_branch(
    branch_id: uuid.UUID,
    body: BranchUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: BranchCommandHandler = Depends(get_branch_command_handler),
    role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Update a branch."""
    branch = await cmd_handler.update(
        branch_id=branch_id,
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, role.value),
        changes=body.model_dump(exclude_unset=True),
    )
    return {"data": branch.model_dump()}


@router.delete("/{branch_id}", responses=ok_message())
async def delete_branch(
    branch_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: BranchCommandHandler = Depends(get_branch_command_handler),
    role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Delete a branch (admin only)."""
    await cmd_handler.delete(
        branch_id=branch_id,
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, role.value),
    )
    return {"data": {"message": t("branch.deleted"), "id": str(branch_id)}}
