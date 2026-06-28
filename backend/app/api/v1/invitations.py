"""Clan invitation endpoints — admin create/list/revoke + invitee accept."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.invitation.commands import (
    AcceptInvitation,
    CreateInvitation,
    RevokeInvitation,
)
from app.application.invitation.handlers import InvitationCommandHandler, InvitationQueryHandler
from app.core.permissions import RequireClanRole
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.dependencies import (
    get_invitation_command_handler,
    get_invitation_query_handler,
)
from app.schemas.auth import UserProfile
from app.schemas.invitation import (
    InvitationAcceptedResponse,
    InvitationCreatedResponse,
    InvitationCreateRequest,
    InvitationResponse,
)
from app.services.translator import t

admin_invitations_router = APIRouter()
user_invitations_router = APIRouter()


@admin_invitations_router.post("", response_model=InvitationCreatedResponse, status_code=201)
async def create_invitation(
    clan_id: uuid.UUID,
    body: InvitationCreateRequest,
    user: UserProfile = Depends(RequireClanRole(["admin"])),
    active_clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: InvitationCommandHandler = Depends(get_invitation_command_handler),
) -> Any:
    if clan_id != active_clan_id:
        raise HTTPException(status_code=403, detail="Path clan does not match your active clan")
    out = await handler.create(
        CreateInvitation(
            clan_id=clan_id,
            email=body.email,
            role=body.role,
            actor=ActorInfo(user_id=user.id, role="admin"),
        )
    )
    return out


@admin_invitations_router.get("")
async def list_invitations(
    clan_id: uuid.UUID,
    user: UserProfile = Depends(RequireClanRole(["admin"])),
    active_clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: InvitationQueryHandler = Depends(get_invitation_query_handler),
) -> dict[str, Any]:
    if clan_id != active_clan_id:
        raise HTTPException(status_code=403, detail="Path clan does not match your active clan")
    invites = await handler.list_for_clan(clan_id)
    return {"data": [InvitationResponse.model_validate(i).model_dump() for i in invites]}


@admin_invitations_router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    clan_id: uuid.UUID,
    invitation_id: uuid.UUID,
    user: UserProfile = Depends(RequireClanRole(["admin"])),
    active_clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: InvitationCommandHandler = Depends(get_invitation_command_handler),
) -> None:
    if clan_id != active_clan_id:
        raise HTTPException(status_code=403, detail="Path clan does not match your active clan")
    await handler.revoke(
        RevokeInvitation(
            clan_id=clan_id,
            invitation_id=invitation_id,
            actor=ActorInfo(user_id=user.id, role="admin"),
        )
    )


@user_invitations_router.post("/{token}/accept", response_model=InvitationAcceptedResponse)
async def accept_invitation(
    token: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    handler: InvitationCommandHandler = Depends(get_invitation_command_handler),
) -> Any:
    out = await handler.accept(
        AcceptInvitation(
            token=token,
            user_id=uuid.UUID(current_user["sub"]),
            user_email=current_user.get("email", ""),
            user_full_name=current_user.get("user_metadata", {}).get("full_name", ""),
        )
    )
    return InvitationAcceptedResponse(
        clan_id=out["clan_id"], role=out["role"], message=t("invitation.accepted")
    )
