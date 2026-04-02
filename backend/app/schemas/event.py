"""Pydantic v2 schemas for Event requests and responses."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class EventCreateRequest(BaseModel):
    person_id: uuid.UUID | None = None
    event_type: str = Field(
        ...,
        pattern="^(death_anniversary|birthday|wedding_anniversary|clan_ceremony|custom)$",
    )
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    event_date: date
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
    is_lunar_calendar: bool | None = None
    is_recurring: bool | None = None
    notify_days_before: int | None = Field(None, ge=0, le=30)


class EventResponse(BaseModel):
    id: uuid.UUID
    clan_id: uuid.UUID
    person_id: uuid.UUID | None = None
    event_type: str
    title: str
    description: str | None = None
    event_date: date
    is_lunar_calendar: bool
    is_recurring: bool
    notify_days_before: int
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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
    event_date: date
    next_occurrence: date
    days_until: int
    is_lunar_calendar: bool


class TimelineEvent(BaseModel):
    event_date: date | None = None
    date_approx: bool = False
    event_type: str
    title: str
    description: str | None = None
    related_person_id: uuid.UUID | None = None
    related_person_name: str | None = None
