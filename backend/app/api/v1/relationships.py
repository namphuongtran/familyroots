"""Relationships API routes — CRUD with business rule validation."""

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
from app.models.member import Member
from app.models.relationship import Relationship
from app.schemas.relationship import RelationshipCreateRequest, RelationshipResponse
from app.services.relationship_validator import RelationshipValidator

router = APIRouter()
validator = RelationshipValidator()


@router.post("", status_code=201)
async def create_relationship(
    body: RelationshipCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a relationship between two members with validation."""
    actor_id = uuid.UUID(current_user["sub"])

    # Verify both members belong to the same clan
    for mid in [body.member_id, body.related_id]:
        result = await db.execute(
            select(Member).where(
                Member.id == mid, Member.clan_id == clan_id, Member.is_deleted.is_(False)
            )
        )
        if not result.scalar_one_or_none():
            raise NotFoundError("member_not_found", {"member_id": str(mid)})

    # Check for duplicate edge
    await validator.check_duplicate_edge(
        body.member_id, body.related_id, body.relation_type, clan_id, db
    )

    # Run business rule validation
    warning = None
    if body.relation_type in ("parent", "child"):
        parent_id = body.member_id if body.relation_type == "parent" else body.related_id
        child_id = body.related_id if body.relation_type == "parent" else body.member_id
        warning = await validator.validate_parent_child(
            parent_id, child_id, body.relation_subtype, db, clan_id
        )
    elif body.relation_type == "spouse":
        await validator.validate_spouse(
            body.member_id, body.related_id, body.start_date, db, clan_id
        )

    rel = Relationship(
        clan_id=clan_id,
        member_id=body.member_id,
        related_id=body.related_id,
        relation_type=body.relation_type,
        relation_subtype=body.relation_subtype,
        start_date=body.start_date,
        end_date=body.end_date,
        is_primary=body.is_primary,
        notes=body.notes,
        created_by=actor_id,
    )
    db.add(rel)
    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=actor_id,
            actor_role="editor",
            action="relationship.create",
            resource_type="relationship",
            resource_id=rel.id,
        )
    )
    await db.commit()
    await db.refresh(rel)

    response = {"data": RelationshipResponse.model_validate(rel).model_dump()}
    if warning:
        response["warning"] = warning
    return response


@router.get("/{relationship_id}")
async def get_relationship(
    relationship_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get a relationship by ID."""
    rel = await _get_rel_or_404(relationship_id, clan_id, db)
    return {"data": RelationshipResponse.model_validate(rel).model_dump()}


@router.patch("/{relationship_id}")
async def update_relationship(
    relationship_id: uuid.UUID,
    body: RelationshipCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Update a relationship."""
    rel = await _get_rel_or_404(relationship_id, clan_id, db)

    for field in ("start_date", "end_date", "is_primary", "notes"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(rel, field, val)

    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=uuid.UUID(current_user["sub"]),
            actor_role="editor",
            action="relationship.update",
            resource_type="relationship",
            resource_id=rel.id,
        )
    )
    await db.commit()
    await db.refresh(rel)
    return {"data": RelationshipResponse.model_validate(rel).model_dump()}


@router.delete("/{relationship_id}")
async def delete_relationship(
    relationship_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Delete a relationship (admin only)."""
    rel = await _get_rel_or_404(relationship_id, clan_id, db)

    await db.delete(rel)
    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=uuid.UUID(current_user["sub"]),
            actor_role="admin",
            action="relationship.delete",
            resource_type="relationship",
            resource_id=relationship_id,
        )
    )
    await db.commit()
    return {"data": {"message": "Relationship deleted", "id": str(relationship_id)}}


async def _get_rel_or_404(rel_id: uuid.UUID, clan_id: uuid.UUID, db: AsyncSession) -> Relationship:
    result = await db.execute(
        select(Relationship).where(Relationship.id == rel_id, Relationship.clan_id == clan_id)
    )
    rel = result.scalar_one_or_none()
    if not rel:
        raise NotFoundError("relationship_not_found")
    return rel
