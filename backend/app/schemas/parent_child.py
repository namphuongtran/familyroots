"""Pydantic v2 schemas for ParentChild requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

RELATIONSHIP_TYPES = {"biological", "adopted", "step", "foster"}


class ParentChildCreateRequest(BaseModel):
    """Request body for creating a parent-child relationship."""

    parent_id: uuid.UUID
    child_id: uuid.UUID
    relationship_type: str = Field("biological", pattern="^(biological|adopted|step|foster)$")
    birth_order: int | None = Field(None, gt=0)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_ids(self) -> ParentChildCreateRequest:
        if str(self.parent_id) == str(self.child_id):
            raise ValueError("parent_id and child_id must be different")
        return self


class ParentChildUpdateRequest(BaseModel):
    """Request body for updating a parent-child relationship."""

    relationship_type: str | None = Field(None, pattern="^(biological|adopted|step|foster)$")
    birth_order: int | None = Field(None, gt=0)
    notes: str | None = None

    # Optimistic concurrency (ADR-017): required so a stale client can't silently
    # clobber a concurrent edit. The route pops this out of `changes` before it
    # reaches the aggregate — it is never itself a client-updatable field.
    expected_version: int = Field(..., ge=1)


class ParentChildResponse(BaseModel):
    """Response schema for a parent-child relationship."""

    id: uuid.UUID
    parent_id: uuid.UUID
    child_id: uuid.UUID
    created_by_clan_id: uuid.UUID
    relationship_type: str
    birth_order: int | None = None
    notes: str | None = None
    created_by: uuid.UUID
    updated_by: uuid.UUID | None = None
    is_deleted: bool = False
    deleted_at: datetime | None = None
    deleted_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    # Optimistic concurrency (ADR-017). Default shields legacy dict read-paths;
    # entity/ORM-backed responses always carry the real stored value.
    version: int = 1

    model_config = {"from_attributes": True}
