"""Branches API routes — CRUD for chi/phái/nhánh within a clan."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.core.permissions import ClanRole, RequireAdmin, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.models.audit_log import AuditLog
from app.models.branch import Branch
from app.schemas.branch import BranchCreateRequest, BranchResponse, BranchUpdateRequest

router = APIRouter()


@router.get("")
async def list_branches(
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """List all branches (chi/phái) for the current clan."""
    result = await db.execute(
        select(Branch)
        .where(Branch.clan_id == clan_id)
        .order_by(Branch.branch_order.asc().nullslast(), Branch.name.asc())
    )
    branches = result.scalars().all()
    return {"data": [BranchResponse.model_validate(b).model_dump() for b in branches]}


@router.post("", status_code=201)
async def create_branch(
    body: BranchCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a new branch within the current clan."""
    actor_id = uuid.UUID(current_user["sub"])

    # Validate parent_branch_id belongs to the same clan
    if body.parent_branch_id:
        parent = await db.execute(
            select(Branch).where(
                Branch.id == body.parent_branch_id, Branch.clan_id == clan_id
            )
        )
        if not parent.scalar_one_or_none():
            raise NotFoundError("branch_not_found", {"branch_id": str(body.parent_branch_id)})

    branch = Branch(
        clan_id=clan_id,
        name=body.name,
        description=body.description,
        founder_person_id=body.founder_person_id,
        parent_branch_id=body.parent_branch_id,
        branch_order=body.branch_order,
    )
    db.add(branch)
    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=actor_id,
            actor_role="editor",
            action="branch.create",
            resource_type="branch",
            resource_id=branch.id,
        )
    )
    await db.commit()
    await db.refresh(branch)
    return {"data": BranchResponse.model_validate(branch).model_dump()}


@router.get("/{branch_id}")
async def get_branch(
    branch_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get a single branch by ID."""
    branch = await _get_branch_or_404(branch_id, clan_id, db)
    return {"data": BranchResponse.model_validate(branch).model_dump()}


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
    branch = await _get_branch_or_404(branch_id, clan_id, db)
    actor_id = uuid.UUID(current_user["sub"])

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(branch, field, value)

    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=actor_id,
            actor_role="editor",
            action="branch.update",
            resource_type="branch",
            resource_id=branch.id,
        )
    )
    await db.commit()
    await db.refresh(branch)
    return {"data": BranchResponse.model_validate(branch).model_dump()}


@router.delete("/{branch_id}")
async def delete_branch(
    branch_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Delete a branch (admin only). Sets branch_id to NULL on related memberships."""
    branch = await _get_branch_or_404(branch_id, clan_id, db)

    await db.delete(branch)
    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=uuid.UUID(current_user["sub"]),
            actor_role="admin",
            action="branch.delete",
            resource_type="branch",
            resource_id=branch_id,
        )
    )
    await db.commit()
    return {"data": {"message": "Branch deleted", "id": str(branch_id)}}


# ── Helpers ───────────────────────────────────────────────────


async def _get_branch_or_404(
    branch_id: uuid.UUID, clan_id: uuid.UUID, db: AsyncSession
) -> Branch:
    result = await db.execute(
        select(Branch).where(Branch.id == branch_id, Branch.clan_id == clan_id)
    )
    branch = result.scalar_one_or_none()
    if not branch:
        raise NotFoundError("branch_not_found")
    return branch
