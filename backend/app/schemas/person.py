"""Pydantic v2 schemas for Person requests and responses."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class PersonCreateRequest(BaseModel):
    """Request body for creating a new person."""

    full_name: str = Field(..., min_length=1, max_length=255)
    birth_name: str | None = Field(None, max_length=255)
    courtesy_name: str | None = Field(None, max_length=255)
    posthumous_name: str | None = Field(None, max_length=255)
    alias_name: str | None = Field(None, max_length=255)
    gender: str = Field("unknown", pattern="^(male|female|unknown)$")

    birth_date: date | None = None
    birth_date_approx: bool = False
    death_date: date | None = None
    death_date_approx: bool = False
    lunar_birth_date: str | None = Field(None, max_length=30)
    lunar_death_date: str | None = Field(None, max_length=30)

    birth_place: str | None = Field(None, max_length=255)
    death_place: str | None = Field(None, max_length=255)
    burial_place: str | None = Field(None, max_length=255)
    tomb_location: str | None = Field(None, max_length=500)
    residence_place: str | None = Field(None, max_length=255)

    religion: str | None = Field(None, max_length=100)
    nationality: str = Field("VN", max_length=100)
    occupation: str | None = Field(None, max_length=255)
    education_level: str | None = Field(None, max_length=255)
    title_rank: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)

    biography: str | None = None
    avatar_url: str | None = Field(None, max_length=500)
    notes: str | None = None

    origin_clan_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_death_after_birth(self) -> "PersonCreateRequest":
        if self.birth_date and self.death_date and self.death_date < self.birth_date:
            raise ValueError("death_date must not be earlier than birth_date")
        return self


class PersonUpdateRequest(BaseModel):
    """Request body for updating a person. All fields optional."""

    full_name: str | None = Field(None, min_length=1, max_length=255)
    birth_name: str | None = Field(None, max_length=255)
    courtesy_name: str | None = Field(None, max_length=255)
    posthumous_name: str | None = Field(None, max_length=255)
    alias_name: str | None = Field(None, max_length=255)
    gender: str | None = Field(None, pattern="^(male|female|unknown)$")

    birth_date: date | None = None
    birth_date_approx: bool | None = None
    death_date: date | None = None
    death_date_approx: bool | None = None
    lunar_birth_date: str | None = Field(None, max_length=30)
    lunar_death_date: str | None = Field(None, max_length=30)

    birth_place: str | None = Field(None, max_length=255)
    death_place: str | None = Field(None, max_length=255)
    burial_place: str | None = Field(None, max_length=255)
    tomb_location: str | None = Field(None, max_length=500)
    residence_place: str | None = Field(None, max_length=255)

    religion: str | None = Field(None, max_length=100)
    nationality: str | None = Field(None, max_length=100)
    occupation: str | None = Field(None, max_length=255)
    education_level: str | None = Field(None, max_length=255)
    title_rank: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)

    biography: str | None = None
    avatar_url: str | None = Field(None, max_length=500)
    notes: str | None = None

    origin_clan_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_death_after_birth(self) -> "PersonUpdateRequest":
        if self.birth_date and self.death_date and self.death_date < self.birth_date:
            raise ValueError("death_date must not be earlier than birth_date")
        return self


class PersonResponse(BaseModel):
    """Response schema for a single person."""

    id: uuid.UUID
    origin_clan_id: uuid.UUID | None = None

    full_name: str
    birth_name: str | None = None
    courtesy_name: str | None = None
    posthumous_name: str | None = None
    alias_name: str | None = None
    gender: str

    birth_date: date | None = None
    birth_date_approx: bool
    death_date: date | None = None
    death_date_approx: bool
    lunar_birth_date: str | None = None
    lunar_death_date: str | None = None

    birth_place: str | None = None
    death_place: str | None = None
    burial_place: str | None = None
    tomb_location: str | None = None
    residence_place: str | None = None

    religion: str | None = None
    nationality: str
    occupation: str | None = None
    education_level: str | None = None
    title_rank: str | None = None
    phone: str | None = None
    email: str | None = None

    biography: str | None = None
    avatar_url: str | None = None
    notes: str | None = None

    is_deleted: bool
    created_by: uuid.UUID
    updated_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PersonListResponse(BaseModel):
    """Paginated response for person listings."""

    persons: list[PersonResponse]
    total: int
    page: int = 1
    page_size: int = 50
