"""Pydantic v2 schemas for ClanMembership requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ClanMembershipCreateRequest(BaseModel):
    """Request body for adding a person to a clan."""

    person_id: uuid.UUID
    clan_id: uuid.UUID
    role: str = Field("blood", pattern="^(blood|spouse|adopted)$")
    generation: int | None = Field(None, gt=0)
    is_founder: bool = False
    branch_id: uuid.UUID | None = None


class ClanMembershipUpdateRequest(BaseModel):
    """Request body for updating a clan membership."""

    role: str | None = Field(None, pattern="^(blood|spouse|adopted)$")
    generation: int | None = Field(None, gt=0)
    is_founder: bool | None = None
    branch_id: uuid.UUID | None = None


class ClanMembershipResponse(BaseModel):
    """Response schema for a clan membership."""

    id: uuid.UUID
    person_id: uuid.UUID
    clan_id: uuid.UUID
    role: str
    generation: int | None = None
    is_founder: bool
    branch_id: uuid.UUID | None = None
    joined_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClanUserSummary(BaseModel):
    """One approved member in GET /clans/me/users."""

    id: str
    user_id: str
    role: str
    person_id: str | None = None
    created_at: str


class UserActionResponse(BaseModel):
    """approve/reject/remove acknowledgement: {message, user_id}."""

    message: str
    user_id: str


class UserRoleChangeResponse(BaseModel):
    """PATCH .../role acknowledgement: {message, user_id, role}."""

    message: str
    user_id: str
    role: str
