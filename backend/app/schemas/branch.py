"""Pydantic v2 schemas for Branch (chi/phái) requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


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

    @field_validator("name")
    @classmethod
    def _reject_null(cls, value: object) -> object:
        # These columns are NOT NULL. Validators run only for keys the client sent,
        # so an omitted field is unaffected and an explicit null is a 422 naming it.
        if value is None:
            raise ValueError("must not be null")
        return value


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
