"""Relationships API routes — thin controller delegating to use-case handlers.

Marriage and ParentChild CRUD operations use the DDD Relationship
bounded context with automatic audit logging via domain events.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends

from app.application.relationship.commands import (
    CreateMarriage,
    CreateParentChild,
    DeleteMarriage,
    DeleteParentChild,
    UpdateMarriage,
    UpdateParentChild,
)
from app.application.relationship.handlers import (
    MarriageCommandHandler,
    MarriageQueryHandler,
    ParentChildCommandHandler,
    ParentChildQueryHandler,
)
from app.core.permissions import ClanRole, RequireAdmin, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.exceptions import EntityNotFoundError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.dependencies import (
    get_marriage_command_handler,
    get_marriage_query_handler,
    get_parent_child_command_handler,
    get_parent_child_query_handler,
)
from app.schemas.marriage import MarriageCreateRequest, MarriageResponse, MarriageUpdateRequest
from app.schemas.parent_child import (
    ParentChildCreateRequest,
    ParentChildResponse,
    ParentChildUpdateRequest,
)

router = APIRouter()


# ── Marriages ─────────────────────────────────────────────────


@router.post("/marriages", status_code=201)
async def create_marriage(
    body: MarriageCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: MarriageCommandHandler = Depends(get_marriage_command_handler),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a marriage between two persons with validation."""
    marriage = await handler.create(
        CreateMarriage(
            person1_id=body.person1_id,
            person2_id=body.person2_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, "editor"),
            marriage_date=body.marriage_date,
            divorce_date=body.divorce_date,
            marriage_place=body.marriage_place,
            status=body.status,
            spouse_order=body.spouse_order,
            notes=body.notes,
        )
    )
    return {"data": marriage.model_dump()}


@router.get("/marriages/{marriage_id}")
async def get_marriage(
    marriage_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: MarriageQueryHandler = Depends(get_marriage_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get a marriage by ID."""
    marriage = await query_handler.get_by_id(marriage_id, clan_id)
    if not marriage:
        raise EntityNotFoundError("marriage_not_found")
    return {"data": MarriageResponse.model_validate(marriage).model_dump()}


@router.patch("/marriages/{marriage_id}")
async def update_marriage(
    marriage_id: uuid.UUID,
    body: MarriageUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: MarriageCommandHandler = Depends(get_marriage_command_handler),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Update a marriage record (only by managing clan)."""
    marriage = await handler.update(
        UpdateMarriage(
            marriage_id=marriage_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, "editor"),
            changes=body.model_dump(exclude_unset=True),
        )
    )
    return {"data": marriage.model_dump()}


@router.delete("/marriages/{marriage_id}")
async def delete_marriage(
    marriage_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: MarriageCommandHandler = Depends(get_marriage_command_handler),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Soft-delete a marriage (admin of managing clan only)."""
    await handler.delete(
        DeleteMarriage(
            marriage_id=marriage_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, "admin"),
        )
    )
    return {"data": {"message": "Marriage deleted", "id": str(marriage_id)}}


# ── Parent-Child ──────────────────────────────────────────────


@router.post("/parent-child", status_code=201)
async def create_parent_child(
    body: ParentChildCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ParentChildCommandHandler = Depends(get_parent_child_command_handler),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a parent-child relationship with validation."""
    link, warning = await handler.create(
        CreateParentChild(
            parent_id=body.parent_id,
            child_id=body.child_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, "editor"),
            relationship_type=body.relationship_type,
            birth_order=body.birth_order,
            notes=body.notes,
        )
    )
    response: dict[str, Any] = {"data": link.model_dump()}
    if warning:
        response["warning"] = warning
    return response


@router.get("/parent-child/{link_id}")
async def get_parent_child(
    link_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: ParentChildQueryHandler = Depends(get_parent_child_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get a parent-child relationship by ID."""
    link = await query_handler.get_by_id(link_id, clan_id)
    if not link:
        raise EntityNotFoundError("parent_child_not_found")
    return {"data": ParentChildResponse.model_validate(link).model_dump()}


@router.patch("/parent-child/{link_id}")
async def update_parent_child(
    link_id: uuid.UUID,
    body: ParentChildUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ParentChildCommandHandler = Depends(get_parent_child_command_handler),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Update a parent-child relationship (only by managing clan)."""
    link = await handler.update(
        UpdateParentChild(
            link_id=link_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, "editor"),
            changes=body.model_dump(exclude_unset=True),
        )
    )
    return {"data": link.model_dump()}


@router.delete("/parent-child/{link_id}")
async def delete_parent_child(
    link_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ParentChildCommandHandler = Depends(get_parent_child_command_handler),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Soft-delete a parent-child relationship (admin of managing clan only)."""
    await handler.delete(
        DeleteParentChild(
            link_id=link_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, "admin"),
        )
    )
    return {"data": {"message": "Parent-child link deleted", "id": str(link_id)}}
