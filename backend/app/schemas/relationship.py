"""Pydantic v2 schemas for Relationship requests and responses."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

PARENT_CHILD_SUBTYPES = {"biological", "adoptive", "step", "foster"}
SPOUSE_SUBTYPES = {"married", "divorced", "widowed", "partner"}


class RelationshipCreateRequest(BaseModel):
    """Request body for creating a relationship edge."""

    member_id: uuid.UUID
    related_id: uuid.UUID
    relation_type: str = Field(..., pattern="^(parent|child|spouse)$")
    relation_subtype: str

    start_date: date | None = None
    end_date: date | None = None
    is_primary: bool = True
    notes: str | None = None

    @model_validator(mode="after")
    def validate_subtype_matches_type(self) -> RelationshipCreateRequest:
        if self.relation_type in ("parent", "child"):
            if self.relation_subtype not in PARENT_CHILD_SUBTYPES:
                raise ValueError(
                    f"relation_subtype must be one of {PARENT_CHILD_SUBTYPES} "
                    f"for relation_type '{self.relation_type}'"
                )
        elif self.relation_type == "spouse" and self.relation_subtype not in SPOUSE_SUBTYPES:
            raise ValueError(
                f"relation_subtype must be one of {SPOUSE_SUBTYPES} for relation_type 'spouse'"
            )
        if str(self.member_id) == str(self.related_id):
            raise ValueError("member_id and related_id must be different")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be earlier than start_date")
        return self


class RelationshipResponse(BaseModel):
    """Response schema for a single relationship."""

    id: uuid.UUID
    clan_id: uuid.UUID
    member_id: uuid.UUID
    related_id: uuid.UUID
    relation_type: str
    relation_subtype: str

    start_date: date | None = None
    end_date: date | None = None
    is_primary: bool
    notes: str | None = None

    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
