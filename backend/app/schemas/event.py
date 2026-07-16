"""Pydantic v2 schemas for Event requests and responses."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.schemas.historical_date import HistoricalDate, coerce_response_dates

_EVENT_DATE_FIELDS: dict[str, str | None] = {"event_date": None}


class EventCreateRequest(BaseModel):
    person_id: uuid.UUID | None = None
    event_type: str = Field(
        ...,
        pattern="^(death_anniversary|birthday|wedding_anniversary|clan_ceremony|custom)$",
    )
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    event_date: date
    event_date_precision: str = Field("exact", pattern="^(exact|year|month|circa|unknown)$")
    event_date_display: str | None = None
    is_lunar_calendar: bool = False
    is_recurring: bool = True
    notify_days_before: int = Field(default=7, ge=0, le=30)


class EventUpdateRequest(BaseModel):
    event_type: str | None = Field(
        None,
        pattern="^(death_anniversary|birthday|wedding_anniversary|clan_ceremony|custom)$",
    )
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    event_date: date | None = None
    event_date_precision: str | None = Field(None, pattern="^(exact|year|month|circa|unknown)$")
    event_date_display: str | None = None
    is_lunar_calendar: bool | None = None
    is_recurring: bool | None = None
    notify_days_before: int | None = Field(None, ge=0, le=30)
    # Optimistic concurrency (ADR-022): the version read from a prior response.
    expected_version: int = Field(..., ge=1)


class EventResponse(BaseModel):
    id: uuid.UUID
    clan_id: uuid.UUID
    person_id: uuid.UUID | None = None
    event_type: str
    title: str
    description: str | None = None
    event_date: HistoricalDate = Field(default_factory=HistoricalDate)
    is_lunar_calendar: bool
    is_recurring: bool
    notify_days_before: int
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # Optimistic concurrency (ADR-022); bumped on every write incl. delete/restore.
    version: int = 1
    is_deleted: bool = False

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _nest_dates(cls, data: Any) -> Any:
        return coerce_response_dates(cls, data, _EVENT_DATE_FIELDS)


class EventPersonSummary(BaseModel):
    """Minimal person payload embedded in event responses."""

    id: uuid.UUID
    full_name: str
    avatar_url: str | None = None


class UpcomingEvent(BaseModel):
    id: uuid.UUID
    person_id: uuid.UUID | None = None
    person_name: str | None = None
    person_avatar_url: str | None = None
    person: EventPersonSummary | None = None
    event_type: str
    title: str
    event_date: HistoricalDate = Field(default_factory=HistoricalDate)
    next_occurrence: date
    days_until: int
    is_lunar_calendar: bool

    @model_validator(mode="before")
    @classmethod
    def _nest_dates(cls, data: Any) -> Any:
        return coerce_response_dates(cls, data, _EVENT_DATE_FIELDS)


class TimelineEvent(BaseModel):
    event_date: HistoricalDate = Field(default_factory=HistoricalDate)
    event_type: str
    title: str
    description: str | None = None
    related_person_id: uuid.UUID | None = None
    related_person_name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _nest_dates(cls, data: Any) -> Any:
        return coerce_response_dates(cls, data, _EVENT_DATE_FIELDS)
