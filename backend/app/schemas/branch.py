"""Pydantic v2 schemas for Branch (chi/phái) requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BranchCreateRequest(BaseModel):
    """Request body for creating a branch within a clan."""

    name: str = Field(..., max_length=255)
    description: str | None = None
    founder_person_id: uuid.UUID | None = None
    parent_branch_id: uuid.UUID | None = None
    branch_order: int | None = Field(None, gt=0)


class BranchUpdateRequest(BaseModel):
    """Request body for updating a branch."""

    name: str | None = Field(None, max_length=255)
    description: str | None = None
    founder_person_id: uuid.UUID | None = None
    parent_branch_id: uuid.UUID | None = None
    branch_order: int | None = Field(None, gt=0)


class BranchResponse(BaseModel):
    """Response schema for a branch."""

    id: uuid.UUID
    clan_id: uuid.UUID
    name: str
    description: str | None = None
    founder_person_id: uuid.UUID | None = None
    parent_branch_id: uuid.UUID | None = None
    branch_order: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
