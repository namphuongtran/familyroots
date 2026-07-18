"""Identity claim endpoints for Clan Admins and Users."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.application.person.claim_handlers import ClaimCommandHandler, ClaimQueryHandler
from app.core.exceptions import ForbiddenError
from app.core.fieldsets import filter_list, parse_field_set
from app.core.permissions import RequireClanRole, require_active_user
from app.core.security import get_current_clan_id
from app.infrastructure.dependencies import get_claim_command_handler, get_claim_query_handler
from app.schemas.auth import UserProfile
from app.schemas.claim import (
    IdentityClaimPrelink,
    IdentityClaimResponse,
    IdentityClaimReview,
    IdentityClaimUnlink,
)
from app.schemas.envelope import created, ok, page

# Router for /m/claims
user_claims_router = APIRouter()

# Router for /m/clans/{clan_id}/claims
admin_claims_router = APIRouter()


@user_claims_router.get(
    "",
    summary="List my identity claims",
    responses=page(IdentityClaimResponse),
)
async def list_my_claims(
    status: str | None = Query(None, description="Filter by status (e.g., PENDING)"),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: UserProfile = Depends(require_active_user),
    handler: ClaimQueryHandler = Depends(get_claim_query_handler),
) -> dict[str, Any]:
    """List identity claims submitted by the current user, across all clans."""
    return await handler.list_my_claims(user_id=user.id, status=status, cursor=cursor, limit=limit)


@user_claims_router.delete(
    "/{claim_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a pending claim",
)
async def cancel_claim(
    claim_id: uuid.UUID,
    user: UserProfile = Depends(require_active_user),
    handler: ClaimCommandHandler = Depends(get_claim_command_handler),
) -> None:
    """Cancel a pending identity claim submitted by the current user."""
    await handler.cancel_claim(claim_id=claim_id, user_id=user.id)


@admin_claims_router.get(
    "",
    summary="List claims for a clan",
    responses=page(IdentityClaimResponse),
)
async def list_clan_claims(
    clan_id: uuid.UUID,
    status: str | None = Query(None, description="Filter by status (e.g., PENDING)"),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: UserProfile = Depends(RequireClanRole(["admin", "editor"])),
    active_clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ClaimQueryHandler = Depends(get_claim_query_handler),
    fields: str | None = Query(None),
) -> dict[str, Any]:
    """List cursor-paginated identity claims for persons created by this clan."""
    if clan_id != active_clan_id:
        raise ForbiddenError("clan_context_mismatch")
    result = await handler.list_clan_claims(
        clan_id=clan_id, status=status, cursor=cursor, limit=limit
    )
    if fields:
        result["data"] = filter_list(result["data"], parse_field_set(fields))
    return result


@admin_claims_router.post(
    "/{claim_id}/approve",
    summary="Approve an identity claim",
    responses=ok(IdentityClaimResponse),
)
async def approve_claim(
    clan_id: uuid.UUID,
    claim_id: uuid.UUID,
    body: IdentityClaimReview,
    user: UserProfile = Depends(RequireClanRole(["admin"])),
    active_clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ClaimCommandHandler = Depends(get_claim_command_handler),
) -> dict[str, Any]:
    """Approve a pending identity claim. Marks the user profile and rejects duplicate claims."""
    if clan_id != active_clan_id:
        raise ForbiddenError("clan_context_mismatch")
    result = await handler.approve_claim(
        claim_id=claim_id,
        admin_id=user.id,
        reviewer_note=body.reviewer_note,
    )
    return {"data": result.model_dump()}


@admin_claims_router.post(
    "/{claim_id}/reject",
    summary="Reject an identity claim",
    responses=ok(IdentityClaimResponse),
)
async def reject_claim(
    clan_id: uuid.UUID,
    claim_id: uuid.UUID,
    body: IdentityClaimReview,
    user: UserProfile = Depends(RequireClanRole(["admin"])),
    active_clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ClaimCommandHandler = Depends(get_claim_command_handler),
) -> dict[str, Any]:
    if clan_id != active_clan_id:
        raise ForbiddenError("clan_context_mismatch")
    result = await handler.reject_claim(
        claim_id=claim_id,
        admin_id=user.id,
        reviewer_note=body.reviewer_note,
    )
    return {"data": result.model_dump()}


@admin_claims_router.post(
    "/members/{user_id}/unlink",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unlink a claimed identity",
)
async def unlink_identity(
    clan_id: uuid.UUID,
    user_id: uuid.UUID,
    body: IdentityClaimUnlink,
    user: UserProfile = Depends(RequireClanRole(["admin"])),
    active_clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ClaimCommandHandler = Depends(get_claim_command_handler),
) -> None:
    """Unlink a claimed identity and revoke the link in UserProfile."""
    if clan_id != active_clan_id:
        raise ForbiddenError("clan_context_mismatch")
    await handler.unlink_identity(
        clan_id=clan_id,
        user_id_to_unlink=user_id,
        admin_id=user.id,
        reason=body.reason,
    )


@admin_claims_router.post(
    "/members/{user_id}/prelink",
    status_code=status.HTTP_201_CREATED,
    summary="Admin Pre-link an identity",
    responses=created(IdentityClaimResponse),
)
async def prelink_identity(
    clan_id: uuid.UUID,
    user_id: uuid.UUID,
    body: IdentityClaimPrelink,
    user: UserProfile = Depends(RequireClanRole(["admin"])),
    active_clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: ClaimCommandHandler = Depends(get_claim_command_handler),
) -> dict[str, Any]:
    """Administratively link a clan member to a person in the tree."""
    if clan_id != active_clan_id:
        raise ForbiddenError("clan_context_mismatch")
    result = await handler.prelink_identity(
        clan_id=clan_id,
        user_id_to_link=user_id,
        person_id=body.person_id,
        admin_id=user.id,
    )
    return {"data": result.model_dump()}
