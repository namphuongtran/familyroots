"""Pydantic v2 schemas for ChangeRequest requests and responses."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChangeRequestCreateRequest(BaseModel):
    """Request body for creating a change request."""

    action: str = Field(..., pattern="^(create|update|delete)$")
    resource_type: str = Field(
        ...,
        pattern="^(person|marriage|parent_child|event|document)$",
    )
    resource_id: uuid.UUID | None = None
    payload: dict[str, Any] | None = None


class ChangeRequestReviewRequest(BaseModel):
    """Request body for reviewing (approve/reject) a change request."""

    status: str = Field(..., pattern="^(approved|rejected)$")
    review_notes: str | None = None


class ChangeRequestResponse(BaseModel):
    """Response schema for a change request."""

    id: uuid.UUID
    clan_id: uuid.UUID
    requester_id: uuid.UUID
    action: str
    resource_type: str
    resource_id: uuid.UUID | None = None
    payload: dict[str, Any] | None = None
    status: str
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
