"""Mapper between Event domain entity and SQLAlchemy ORM model."""

from __future__ import annotations

from app.domain.event.entity import Event as EventEntity
from app.models.event import Event as EventModel

_MAPPED_FIELDS = (
    "clan_id", "person_id", "event_type", "title", "description",
    "event_date", "is_lunar_calendar", "is_recurring", "notify_days_before",
    "created_by",
)


def to_domain(model: EventModel) -> EventEntity:
    """Convert a SQLAlchemy Event ORM instance to a domain entity."""
    return EventEntity(
        id=model.id,
        clan_id=model.clan_id,
        person_id=model.person_id,
        event_type=model.event_type,
        title=model.title,
        description=model.description,
        event_date=model.event_date,
        is_lunar_calendar=model.is_lunar_calendar,
        is_recurring=model.is_recurring,
        notify_days_before=model.notify_days_before,
        created_by=model.created_by,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def to_orm(entity: EventEntity) -> EventModel:
    """Convert a domain Event entity to a SQLAlchemy ORM instance (INSERT)."""
    return EventModel(
        id=entity.id,
        clan_id=entity.clan_id,
        person_id=entity.person_id,
        event_type=entity.event_type,
        title=entity.title,
        description=entity.description,
        event_date=entity.event_date,
        is_lunar_calendar=entity.is_lunar_calendar,
        is_recurring=entity.is_recurring,
        notify_days_before=entity.notify_days_before,
        created_by=entity.created_by,
    )


def apply_to_orm(entity: EventEntity, model: EventModel) -> None:
    """Apply domain entity state onto an existing ORM model (UPDATE)."""
    for field_name in _MAPPED_FIELDS:
        setattr(model, field_name, getattr(entity, field_name))
