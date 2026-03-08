"""Relationships API routes — marriages and parent-child CRUD with validation."""

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
from app.models.marriage import Marriage
from app.models.parent_child import ParentChild
from app.models.person import Person
from app.schemas.marriage import MarriageCreateRequest, MarriageResponse, MarriageUpdateRequest
from app.schemas.parent_child import (
    ParentChildCreateRequest,
    ParentChildResponse,
    ParentChildUpdateRequest,
)
from app.services.relationship_validator import RelationshipValidator

router = APIRouter()
validator = RelationshipValidator()


# ── Marriages ─────────────────────────────────────────────────


@router.post("/marriages", status_code=201)
async def create_marriage(
    body: MarriageCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a marriage between two persons with validation."""
    actor_id = uuid.UUID(current_user["sub"])

    # Verify both persons exist
    for pid in [body.person1_id, body.person2_id]:
        result = await db.execute(
            select(Person).where(Person.id == pid, Person.is_deleted.is_(False))
        )
        if not result.scalar_one_or_none():
            raise NotFoundError("person_not_found", {"person_id": str(pid)})

    await validator.validate_spouse(body.person1_id, body.person2_id, body.marriage_date, db)
    await validator.check_duplicate_marriage(body.person1_id, body.person2_id, db)

    marriage = Marriage(
        person1_id=body.person1_id,
        person2_id=body.person2_id,
        created_by_clan_id=clan_id,
        marriage_date=body.marriage_date,
        divorce_date=body.divorce_date,
        marriage_place=body.marriage_place,
        status=body.status,
        spouse_order=body.spouse_order,
        notes=body.notes,
        created_by=actor_id,
    )
    db.add(marriage)
    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=actor_id,
            actor_role="editor",
            action="marriage.create",
            resource_type="marriage",
            resource_id=marriage.id,
        )
    )
    await db.commit()
    await db.refresh(marriage)
    return {"data": MarriageResponse.model_validate(marriage).model_dump()}


@router.get("/marriages/{marriage_id}")
async def get_marriage(
    marriage_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get a marriage by ID."""
    marriage = await _get_marriage_or_404(marriage_id, db)
    return {"data": MarriageResponse.model_validate(marriage).model_dump()}


@router.patch("/marriages/{marriage_id}")
async def update_marriage(
    marriage_id: uuid.UUID,
    body: MarriageUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Update a marriage record (only by managing clan)."""
    marriage = await _get_marriage_or_404(marriage_id, db)
    if marriage.created_by_clan_id != clan_id:
        raise NotFoundError("marriage_not_found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(marriage, field, value)

    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=uuid.UUID(current_user["sub"]),
            actor_role="editor",
            action="marriage.update",
            resource_type="marriage",
            resource_id=marriage.id,
        )
    )
    await db.commit()
    await db.refresh(marriage)
    return {"data": MarriageResponse.model_validate(marriage).model_dump()}


@router.delete("/marriages/{marriage_id}")
async def delete_marriage(
    marriage_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Delete a marriage (admin of managing clan only)."""
    marriage = await _get_marriage_or_404(marriage_id, db)
    if marriage.created_by_clan_id != clan_id:
        raise NotFoundError("marriage_not_found")

    await db.delete(marriage)
    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=uuid.UUID(current_user["sub"]),
            actor_role="admin",
            action="marriage.delete",
            resource_type="marriage",
            resource_id=marriage_id,
        )
    )
    await db.commit()
    return {"data": {"message": "Marriage deleted", "id": str(marriage_id)}}


# ── Parent-Child ──────────────────────────────────────────────


@router.post("/parent-child", status_code=201)
async def create_parent_child(
    body: ParentChildCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a parent-child relationship with validation."""
    actor_id = uuid.UUID(current_user["sub"])

    # Verify both persons exist
    for pid in [body.parent_id, body.child_id]:
        result = await db.execute(
            select(Person).where(Person.id == pid, Person.is_deleted.is_(False))
        )
        if not result.scalar_one_or_none():
            raise NotFoundError("person_not_found", {"person_id": str(pid)})

    warning = await validator.validate_parent_child(
        body.parent_id, body.child_id, body.relationship_type, db, clan_id
    )
    await validator.check_duplicate_parent_child(body.parent_id, body.child_id, db)

    link = ParentChild(
        parent_id=body.parent_id,
        child_id=body.child_id,
        created_by_clan_id=clan_id,
        relationship_type=body.relationship_type,
        notes=body.notes,
        created_by=actor_id,
    )
    db.add(link)
    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=actor_id,
            actor_role="editor",
            action="parent_child.create",
            resource_type="parent_child",
            resource_id=link.id,
        )
    )
    await db.commit()
    await db.refresh(link)

    response = {"data": ParentChildResponse.model_validate(link).model_dump()}
    if warning:
        response["warning"] = warning
    return response


@router.get("/parent-child/{link_id}")
async def get_parent_child(
    link_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get a parent-child relationship by ID."""
    link = await _get_parent_child_or_404(link_id, db)
    return {"data": ParentChildResponse.model_validate(link).model_dump()}


@router.patch("/parent-child/{link_id}")
async def update_parent_child(
    link_id: uuid.UUID,
    body: ParentChildUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Update a parent-child relationship (only by managing clan)."""
    link = await _get_parent_child_or_404(link_id, db)
    if link.created_by_clan_id != clan_id:
        raise NotFoundError("parent_child_not_found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(link, field, value)

    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=uuid.UUID(current_user["sub"]),
            actor_role="editor",
            action="parent_child.update",
            resource_type="parent_child",
            resource_id=link.id,
        )
    )
    await db.commit()
    await db.refresh(link)
    return {"data": ParentChildResponse.model_validate(link).model_dump()}


@router.delete("/parent-child/{link_id}")
async def delete_parent_child(
    link_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Delete a parent-child relationship (admin of managing clan only)."""
    link = await _get_parent_child_or_404(link_id, db)
    if link.created_by_clan_id != clan_id:
        raise NotFoundError("parent_child_not_found")

    await db.delete(link)
    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=uuid.UUID(current_user["sub"]),
            actor_role="admin",
            action="parent_child.delete",
            resource_type="parent_child",
            resource_id=link_id,
        )
    )
    await db.commit()
    return {"data": {"message": "Parent-child link deleted", "id": str(link_id)}}


# ── Helpers ───────────────────────────────────────────────────


async def _get_marriage_or_404(marriage_id: uuid.UUID, db: AsyncSession) -> Marriage:
    result = await db.execute(select(Marriage).where(Marriage.id == marriage_id))
    marriage = result.scalar_one_or_none()
    if not marriage:
        raise NotFoundError("marriage_not_found")
    return marriage


async def _get_parent_child_or_404(link_id: uuid.UUID, db: AsyncSession) -> ParentChild:
    result = await db.execute(select(ParentChild).where(ParentChild.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise NotFoundError("parent_child_not_found")
    return link
