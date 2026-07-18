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


class CountMeta(BaseModel):
    """LEGACY meta for GET /me/clans (ADR-024): a bare {count} instead of the
    canonical {cursor, has_more, limit}. Typed as-is; scheduled for normalization
    to cursor meta before the frontend binds. Do not copy this shape."""

    count: int


class UserClansEnvelope(BaseModel):
    """GET /me/clans: {data: [UserClanMembership], meta: {count}} — non-canonical
    (see CountMeta / ADR-024)."""

    data: list[UserClanMembership]
    meta: CountMeta


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
    motto: str | None = None
    ancestral_hall_location: str | None = None
    clan_rules: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClanStats(BaseModel):
    """Aggregate counters used by clan dashboard views."""

    total_users: int
    approved_users: int
    pending_users: int
    total_members: int


class ClanUpdateRequest(BaseModel):
    """Request body for updating clan info."""

    name: str | None = None
    description: str | None = None
    origin_place: str | None = None
    founded_year: int | None = None
    avatar_url: str | None = None
    motto: str | None = None
    ancestral_hall_location: str | None = None
    clan_rules: str | None = None
