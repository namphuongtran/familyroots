"""Pydantic schemas for Identity Claims."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class IdentityClaimBase(BaseModel):
    requester_note: str | None = Field(default=None, max_length=1000)


class IdentityClaimSubmit(IdentityClaimBase):
    pass


class IdentityClaimReview(BaseModel):
    reviewer_note: str | None = Field(default=None, max_length=1000)


class IdentityClaimUnlink(BaseModel):
    reason: str = Field(
        ..., max_length=1000, description="Mandatory reason for unlinking identity."
    )


class IdentityClaimPrelink(BaseModel):
    person_id: uuid.UUID = Field(..., description="ID of the Person to link the user to.")


class IdentityClaimResponse(IdentityClaimBase):
    id: uuid.UUID
    user_id: uuid.UUID
    person_id: uuid.UUID
    status: str
    reviewer_note: str | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IdentityClaimPaginatedResponse(BaseModel):
    items: list[IdentityClaimResponse]
    total: int
    page: int
    page_size: int
