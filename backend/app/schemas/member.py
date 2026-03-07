"""Pydantic v2 schemas for Member requests and responses."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class MemberCreateRequest(BaseModel):
    """Request body for creating a new family member."""

    full_name: str = Field(..., min_length=1, max_length=255)
    birth_name: str | None = Field(None, max_length=255)
    courtesy_name: str | None = Field(None, max_length=255)
    gender: str = Field("unknown", pattern="^(male|female|unknown)$")

    birth_date: date | None = None
    birth_date_approx: bool = False
    death_date: date | None = None
    death_date_approx: bool = False

    birth_place: str | None = Field(None, max_length=255)
    death_place: str | None = Field(None, max_length=255)
    residence_place: str | None = Field(None, max_length=255)

    generation: int | None = Field(None, gt=0)
    is_clan_founder: bool = False
    is_clan_member: bool = True

    biography: str | None = None
    avatar_url: str | None = Field(None, max_length=500)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_death_after_birth(self) -> MemberCreateRequest:
        if self.birth_date and self.death_date and self.death_date < self.birth_date:
            raise ValueError("death_date must not be earlier than birth_date")
        return self


class MemberUpdateRequest(BaseModel):
    """Request body for updating a family member. All fields optional."""

    full_name: str | None = Field(None, min_length=1, max_length=255)
    birth_name: str | None = Field(None, max_length=255)
    courtesy_name: str | None = Field(None, max_length=255)
    gender: str | None = Field(None, pattern="^(male|female|unknown)$")

    birth_date: date | None = None
    birth_date_approx: bool | None = None
    death_date: date | None = None
    death_date_approx: bool | None = None

    birth_place: str | None = Field(None, max_length=255)
    death_place: str | None = Field(None, max_length=255)
    residence_place: str | None = Field(None, max_length=255)

    generation: int | None = Field(None, gt=0)
    is_clan_founder: bool | None = None
    is_clan_member: bool | None = None

    biography: str | None = None
    avatar_url: str | None = Field(None, max_length=500)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_death_after_birth(self) -> MemberUpdateRequest:
        if self.birth_date and self.death_date and self.death_date < self.birth_date:
            raise ValueError("death_date must not be earlier than birth_date")
        return self


class MemberResponse(BaseModel):
    """Response schema for a single member."""

    id: uuid.UUID
    clan_id: uuid.UUID
    full_name: str
    birth_name: str | None = None
    courtesy_name: str | None = None
    gender: str

    birth_date: date | None = None
    birth_date_approx: bool
    death_date: date | None = None
    death_date_approx: bool

    birth_place: str | None = None
    death_place: str | None = None
    residence_place: str | None = None

    generation: int | None = None
    is_clan_founder: bool
    is_clan_member: bool

    biography: str | None = None
    avatar_url: str | None = None
    notes: str | None = None

    is_deleted: bool
    created_by: uuid.UUID
    updated_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemberListResponse(BaseModel):
    """Paginated response for member listings."""

    members: list[MemberResponse]
    total: int
    page: int = 1
    page_size: int = 50
