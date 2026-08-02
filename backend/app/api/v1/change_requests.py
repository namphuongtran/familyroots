"""Change-request endpoints — propose a correction, review it (ADR-037).

Role model (docs/architecture/rbac.md):

- **Submit / read** — ``RequireViewer``, i.e. any approved clan member. In practice
  viewers are the users: everyone else can just make the edit.
- **Approve / reject** — ``RequireEditor``, which is hierarchical and therefore means
  editor **or** admin. An editor can already make the identical edit unilaterally, so
  requiring an admin would protect nothing and would stall a clan whose single admin
  is busy.

A viewer may read only their own proposals; editors and admins see the clan queue.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.application.change_request.commands import (
    GetChangeRequest,
    ListChangeRequests,
    ReviewChangeRequest,
    SubmitChangeRequest,
)
from app.application.change_request.handlers import (
    ChangeRequestCommandHandler,
    ChangeRequestQueryHandler,
)
from app.core.permissions import ClanRole, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.dependencies import (
    get_change_request_command_handler,
    get_change_request_query_handler,
)
from app.schemas.change_request import (
    ChangeRequestCreateRequest,
    ChangeRequestResponse,
    ChangeRequestReviewRequest,
)
from app.schemas.envelope import created, ok, page

router = APIRouter()


@router.post("", status_code=201, responses=created(ChangeRequestResponse))
async def submit_change_request(
    body: ChangeRequestCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ChangeRequestCommandHandler = Depends(get_change_request_command_handler),
    role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Propose a correction to a person in the active clan."""
    result = await handler.submit(
        SubmitChangeRequest(
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, role.value),
            action=body.action,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            changes=body.changes,
            note=body.note,
        )
    )
    return {"data": result.model_dump()}


@router.get("", responses=page(ChangeRequestResponse))
async def list_change_requests(
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ChangeRequestQueryHandler = Depends(get_change_request_query_handler),
    role: ClanRole = RequireViewer,
    status: str | None = Query(
        None,
        pattern="^(pending|approved|rejected)$",
        description="Filter by review status.",
    ),
    cursor: str | None = Query(None),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """List change requests: the clan queue for reviewers, own proposals for viewers."""
    data, meta = await handler.list(
        ListChangeRequests(
            clan_id=clan_id,
            viewer_user_id=uuid.UUID(current_user["sub"]),
            viewer_role=role.value,
            status=status,
            cursor=cursor,
            limit=limit,
        )
    )
    return {"data": [item.model_dump() for item in data], "meta": meta}


@router.get("/{change_request_id}", responses=ok(ChangeRequestResponse))
async def get_change_request(
    change_request_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ChangeRequestQueryHandler = Depends(get_change_request_query_handler),
    role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get one change request, including the live state of the record it targets."""
    result = await handler.get(
        GetChangeRequest(
            change_request_id=change_request_id,
            clan_id=clan_id,
            viewer_user_id=uuid.UUID(current_user["sub"]),
            viewer_role=role.value,
        )
    )
    return {"data": result.model_dump()}


@router.post("/{change_request_id}/approve", responses=ok(ChangeRequestResponse))
async def approve_change_request(
    change_request_id: uuid.UUID,
    body: ChangeRequestReviewRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ChangeRequestCommandHandler = Depends(get_change_request_command_handler),
    # Hierarchical: editor OR admin. See the module docstring.
    role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Approve a change request and apply it to the target record."""
    result = await handler.approve(
        ReviewChangeRequest(
            change_request_id=change_request_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, role.value),
            review_notes=body.review_notes,
        )
    )
    return {"data": result.model_dump()}


@router.post("/{change_request_id}/reject", responses=ok(ChangeRequestResponse))
async def reject_change_request(
    change_request_id: uuid.UUID,
    body: ChangeRequestReviewRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ChangeRequestCommandHandler = Depends(get_change_request_command_handler),
    role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Reject a change request. The target record is left untouched."""
    result = await handler.reject(
        ReviewChangeRequest(
            change_request_id=change_request_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, role.value),
            review_notes=body.review_notes,
        )
    )
    return {"data": result.model_dump()}
