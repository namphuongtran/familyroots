"""Events API routes — thin controller delegating to Event handlers."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.application.event.handlers import EventCommandHandler, EventQueryHandler
from app.core.permissions import ClanRole, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.value_objects import ActorInfo
from app.schemas.event import EventCreateRequest, EventUpdateRequest

router = APIRouter()


from app.infrastructure.dependencies import get_event_command_handler, get_event_query_handler


@router.post("", status_code=201)
async def create_event(
    body: EventCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: EventCommandHandler = Depends(get_event_command_handler),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a new event."""
    event = await cmd_handler.create(
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, "editor"),
        person_id=body.person_id,
        event_type=body.event_type,
        title=body.title,
        description=body.description,
        event_date=body.event_date,
        is_lunar_calendar=body.is_lunar_calendar,
        is_recurring=body.is_recurring,
        notify_days_before=body.notify_days_before,
    )
    return {"data": event.model_dump()}


@router.get("")
async def list_events(
    person_id: uuid.UUID | None = Query(None),
    event_type: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: EventQueryHandler = Depends(get_event_query_handler),
    _role: ClanRole = RequireViewer,
    fields: str | None = Query(None),
) -> dict[str, Any]:
    """List events with optional filters."""
    items = await query_handler.list_events(
        clan_id=clan_id, person_id=person_id, event_type=event_type,
        cursor=cursor, limit=limit,
    )
    data = [item.model_dump() for item in items]
    if fields:
        field_set = {f.strip() for f in fields.split(",")}
        data = [{k: v for k, v in d.items() if k in field_set} for d in data]
    return {"data": data}


@router.get("/upcoming")
async def get_upcoming_events(
    days: int = Query(30, ge=1, le=365),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: EventQueryHandler = Depends(get_event_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get upcoming events within the next N days."""
    upcoming = await query_handler.get_upcoming(clan_id=clan_id, days=days)
    return {"data": upcoming}


@router.get("/{event_id}")
async def get_event(
    event_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: EventQueryHandler = Depends(get_event_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    event = await query_handler.get(event_id=event_id, clan_id=clan_id)
    return {"data": event.model_dump()}


@router.patch("/{event_id}")
async def update_event(
    event_id: uuid.UUID,
    body: EventUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: EventCommandHandler = Depends(get_event_command_handler),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    event = await cmd_handler.update(
        event_id=event_id,
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, "editor"),
        changes=body.model_dump(exclude_unset=True),
    )
    return {"data": event.model_dump()}


@router.delete("/{event_id}")
async def delete_event(
    event_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: EventCommandHandler = Depends(get_event_command_handler),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    await cmd_handler.delete(
        event_id=event_id,
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, "editor"),
    )
    return {"data": {"message": "Event deleted", "id": str(event_id)}}
