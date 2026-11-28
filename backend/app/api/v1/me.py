"""Me API routes — thin controller delegating to Me handler."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends

from app.application.auth.account_handlers import AccountCommandHandler
from app.application.me.handlers import MeQueryHandler
from app.core.security import get_current_user, get_verified_token
from app.infrastructure.dependencies import get_account_command_handler, get_me_query_handler
from app.schemas.clan import ClanSwitchResponse, UserClanMembership
from app.schemas.envelope import ok, ok_list, ok_message
from app.services.translator import t

router = APIRouter()


@router.get("/clans", responses=ok_list(UserClanMembership))
async def list_my_clans(
    current_user: dict[str, Any] = Depends(get_current_user),
    handler: MeQueryHandler = Depends(get_me_query_handler),
) -> dict[str, Any]:
    """List all clans the authenticated user belongs to (a clan switcher — all
    approved memberships, unpaginated)."""
    result = await handler.list_clans(user_id=current_user["sub"])
    return {"data": result}


@router.post("/clans/{clan_id}/select", responses=ok(ClanSwitchResponse))
async def select_clan(
    clan_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    handler: MeQueryHandler = Depends(get_me_query_handler),
) -> dict[str, Any]:
    """Select a clan as the active context."""
    result = await handler.select_clan(user_id=current_user["sub"], clan_id=clan_id)
    return {"data": result}


@router.delete("", responses=ok_message())
async def delete_my_account(
    token: dict[str, Any] = Depends(get_verified_token),
    handler: AccountCommandHandler = Depends(get_account_command_handler),
) -> dict[str, Any]:
    """Delete the caller's own account (ADR-079): the provider account, every clan role
    and membership, identity claims, push tokens and the profile's personal data.

    403 ``account.last_admin_transfer_first`` while the caller is the only approved
    admin of a clan; ``detail.clan_ids`` names those clans. The family-tree person the
    account was linked to stays — it is clan data, and an admin can anonymise it."""
    await handler.delete_account(user_id=uuid.UUID(token["sub"]))
    return {"data": {"message": t("account.deleted")}}
