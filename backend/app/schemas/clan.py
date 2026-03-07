"""Pydantic v2 schemas for Clan requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class UserClanMembership(BaseModel):
    """A single clan membership for the authenticated user."""

    clan_id: uuid.UUID
    clan_name: str
    clan_slug: str
    role: str  # admin | editor | viewer
    joined_at: datetime | None = None


class UserClansResponse(BaseModel):
    """Response for GET /me/clans — all clans the user belongs to."""

    clans: list[UserClanMembership]
    count: int


class ClanSwitchResponse(BaseModel):
    """Response for POST /me/clans/{clan_id}/select — confirm clan selection."""

    clan_id: uuid.UUID
    clan_name: str
    clan_slug: str
    role: str
    message: str


# TODO: implement in Prompt 2
#
# Expected schemas:
# - ClanCreateRequest
# - ClanResponse
# - ClanListResponse
