"""Identity claim endpoints for Clan Admins and Users."""

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.application.person.claim_handlers import ClaimCommandHandler, ClaimQueryHandler
from app.core.permissions import RequireClanRole, require_active_user
from app.infrastructure.dependencies import get_claim_command_handler, get_claim_query_handler
from typing import Any

from app.schemas.auth import UserProfile
from app.schemas.claim import (
    IdentityClaimPaginatedResponse,
    IdentityClaimPrelink,
    IdentityClaimResponse,
    IdentityClaimReview,
    IdentityClaimUnlink,
)

# Router for /m/claims
user_claims_router = APIRouter()

# Router for /m/clans/{clan_id}/claims
admin_claims_router = APIRouter()


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
)
async def list_clan_claims(
    clan_id: uuid.UUID,
    status: str | None = Query(None, description="Filter by status (e.g., PENDING)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserProfile = Depends(RequireClanRole(["admin", "editor"])),
    handler: ClaimQueryHandler = Depends(get_claim_query_handler),
    fields: str | None = Query(None),
) -> dict[str, Any]:
    """List paginated identity claims for persons created by this clan."""
    paginated = await handler.list_clan_claims(
        clan_id=clan_id, status=status, page=page, page_size=page_size
    )
    res_dict = paginated.model_dump()
    if fields:
        from app.core.fieldsets import filter_list, parse_field_set

        res_dict["claims"] = filter_list(res_dict["claims"], parse_field_set(fields))
    return res_dict


@admin_claims_router.post(
    "/{claim_id}/approve",
    response_model=IdentityClaimResponse,
    summary="Approve an identity claim",
)
async def approve_claim(
    clan_id: uuid.UUID,
    claim_id: uuid.UUID,
    body: IdentityClaimReview,
    user: UserProfile = Depends(RequireClanRole(["admin"])),
    handler: ClaimCommandHandler = Depends(get_claim_command_handler),
) -> IdentityClaimResponse:
    """Approve a pending identity claim. Marks the user profile and rejects duplicate claims."""
    return await handler.approve_claim(
        claim_id=claim_id,
        admin_id=user.id,
        reviewer_note=body.reviewer_note,
    )


@admin_claims_router.post(
    "/{claim_id}/reject",
    response_model=IdentityClaimResponse,
    summary="Reject an identity claim",
)
async def reject_claim(
    clan_id: uuid.UUID,
    claim_id: uuid.UUID,
    body: IdentityClaimReview,
    user: UserProfile = Depends(RequireClanRole(["admin"])),
    handler: ClaimCommandHandler = Depends(get_claim_command_handler),
) -> IdentityClaimResponse:
    return await handler.reject_claim(
        claim_id=claim_id,
        admin_id=user.id,
        reviewer_note=body.reviewer_note,
    )

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
    handler: ClaimCommandHandler = Depends(get_claim_command_handler),
) -> None:
    """Unlink a claimed identity and revoke the link in UserProfile."""
    await handler.unlink_identity(
        clan_id=clan_id,
        user_id_to_unlink=user_id,
        admin_id=user.id,
        reason=body.reason,
    )

@admin_claims_router.post(
    "/members/{user_id}/prelink",
    response_model=IdentityClaimResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin Pre-link an identity",
)
async def prelink_identity(
    clan_id: uuid.UUID,
    user_id: uuid.UUID,
    body: IdentityClaimPrelink,
    user: UserProfile = Depends(RequireClanRole(["admin"])),
    handler: ClaimCommandHandler = Depends(get_claim_command_handler),
) -> IdentityClaimResponse:
    """Administratively link a clan member to a person in the tree."""
    return await handler.prelink_identity(
        clan_id=clan_id,
        user_id_to_link=user_id,
        person_id=body.person_id,
        admin_id=user.id,
    )
