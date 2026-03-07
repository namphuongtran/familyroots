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


class ClanResponse(BaseModel):
    """Full clan detail response."""

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    origin_place: str | None = None
    founded_year: int | None = None
    avatar_url: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClanUpdateRequest(BaseModel):
    """Request body for updating clan info."""

    name: str | None = None
    description: str | None = None
    origin_place: str | None = None
    founded_year: int | None = None
    avatar_url: str | None = None
