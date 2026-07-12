"""Pydantic v2 schemas for Marriage requests and responses."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.schemas.historical_date import HistoricalDate, coerce_response_dates

MARRIAGE_STATUSES = {"married", "divorced", "widowed", "separated"}

_MARRIAGE_DATE_FIELDS: dict[str, str | None] = {"marriage_date": None, "divorce_date": None}


class MarriageCreateRequest(BaseModel):
    """Request body for creating a marriage record."""

    person1_id: uuid.UUID
    person2_id: uuid.UUID
    marriage_date: date | None = None
    marriage_date_precision: str = Field("exact", pattern="^(exact|year|month|circa|unknown)$")
    marriage_date_display: str | None = None
    divorce_date: date | None = None
    divorce_date_precision: str = Field("exact", pattern="^(exact|year|month|circa|unknown)$")
    divorce_date_display: str | None = None
    marriage_place: str | None = Field(None, max_length=255)
    status: str = Field("married", pattern="^(married|divorced|widowed|separated)$")
    spouse_order: int | None = Field(None, gt=0)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_marriage(self) -> MarriageCreateRequest:
        if str(self.person1_id) == str(self.person2_id):
            raise ValueError("person1_id and person2_id must be different")
        if self.marriage_date and self.divorce_date and self.divorce_date < self.marriage_date:
            raise ValueError("divorce_date must not be earlier than marriage_date")
        return self


class MarriageUpdateRequest(BaseModel):
    """Request body for updating a marriage record."""

    marriage_date: date | None = None
    marriage_date_precision: str | None = Field(None, pattern="^(exact|year|month|circa|unknown)$")
    marriage_date_display: str | None = None
    divorce_date: date | None = None
    divorce_date_precision: str | None = Field(None, pattern="^(exact|year|month|circa|unknown)$")
    divorce_date_display: str | None = None
    marriage_place: str | None = Field(None, max_length=255)
    status: str | None = Field(None, pattern="^(married|divorced|widowed|separated)$")
    spouse_order: int | None = Field(None, gt=0)
    notes: str | None = None

    # Optimistic concurrency (ADR-017): required so a stale client can't silently
    # clobber a concurrent edit. The route pops this out of `changes` before it
    # reaches the aggregate — it is never itself a client-updatable field.
    expected_version: int = Field(..., ge=1)


class MarriageResponse(BaseModel):
    """Response schema for a marriage record."""

    id: uuid.UUID
    person1_id: uuid.UUID
    person2_id: uuid.UUID
    created_by_clan_id: uuid.UUID
    marriage_date: HistoricalDate = Field(default_factory=HistoricalDate)
    divorce_date: HistoricalDate = Field(default_factory=HistoricalDate)
    marriage_place: str | None = None
    status: str
    spouse_order: int | None = None
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

    @model_validator(mode="before")
    @classmethod
    def _nest_dates(cls, data: Any) -> Any:
        return coerce_response_dates(cls, data, _MARRIAGE_DATE_FIELDS)
