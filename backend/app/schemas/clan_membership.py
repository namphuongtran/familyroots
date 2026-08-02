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
    """One approved member in GET /clans/me/users (viewer-readable).

    Carries ``display_name`` but deliberately **no** ``email``: this list is
    readable by every approved member of the clan, so an ``email`` field here
    would broadcast each member's login address to the whole clan. The
    admin-only pending queue uses the separate ``PendingClanUserSummary``.
    See ADR-039 before adding any contact field to this model.
    """

    id: str
    user_id: str
    role: str
    person_id: str | None = None
    display_name: str | None = None
    created_at: str


class PendingClanUserSummary(BaseModel):
    """One pending join request in GET /clans/me/users/pending (admin-only).

    Intentionally NOT a subclass of :class:`ClanUserSummary`, and intentionally
    duplicating its fields: subclassing would mean any field added to the
    viewer-readable model silently widens this one too — and, worse, invites the
    inverse "tidy-up" that merges the two and leaks ``email`` to every viewer.
    The asymmetry is the point; see ADR-039.

    ``email`` is justified here and only here: the admin is making an identity
    decision (approving grants read access to hundreds of living relatives'
    records), already holds approve/reject/role powers, and the address is the
    account holder's own registration email — not a genealogy record about a
    third party.
    """

    id: str
    user_id: str
    role: str
    person_id: str | None = None
    display_name: str | None = None
    email: str | None = None
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
