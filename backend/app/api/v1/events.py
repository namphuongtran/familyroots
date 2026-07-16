"""Events API routes — thin controller delegating to Event handlers."""

import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from app.application.event.handlers import EventCommandHandler, EventQueryHandler
from app.application.person.commands import GetPerson
from app.application.person.handlers import PersonQueryHandler
from app.core.config import settings
from app.core.permissions import ClanRole, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.exceptions import EntityNotFoundError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.dependencies import (
    get_event_command_handler,
    get_event_query_handler,
    get_person_query_handler,
)
from app.schemas.event import EventCreateRequest, EventUpdateRequest
from app.services.translator import t

router = APIRouter()


async def _included_person(
    person_handler: PersonQueryHandler, person_id: uuid.UUID, clan_id: uuid.UUID
) -> dict[str, Any] | None:
    """The include=person summary, or None when the person is genuinely gone.

    Only EntityNotFoundError (e.g. the person was soft-deleted after the event
    was created) becomes null — the event itself is still valid. Any other
    failure propagates so the standard error envelope is produced instead of
    masking a fault as "no linked person" (same policy as persons includes).
    """
    try:
        person = await person_handler.get(GetPerson(person_id=person_id, clan_id=clan_id))
    except EntityNotFoundError:
        return None
    return {
        "id": str(person.id),
        "full_name": person.full_name,
        "gender": person.gender,
        "avatar_url": person.avatar_url,
    }


@router.post("", status_code=201)
async def create_event(
    body: EventCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: EventCommandHandler = Depends(get_event_command_handler),
    role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a new event."""
    event = await cmd_handler.create(
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, role.value),
        person_id=body.person_id,
        event_type=body.event_type,
        title=body.title,
        description=body.description,
        event_date=body.event_date,
        event_date_precision=body.event_date_precision,
        event_date_display=body.event_date_display,
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
    role: ClanRole = RequireViewer,
    fields: str | None = Query(None),
) -> dict[str, Any]:
    """List events with optional filters."""
    items, meta = await query_handler.list_events(
        clan_id=clan_id,
        person_id=person_id,
        event_type=event_type,
        cursor=cursor,
        limit=limit,
    )
    data = [item.model_dump() for item in items]
    if fields:
        field_set = {f.strip() for f in fields.split(",")}
        data = [{k: v for k, v in d.items() if k in field_set} for d in data]
    return {"data": data, "meta": meta}


@router.get("/upcoming")
async def get_upcoming_events(
    days: int = Query(30, ge=1, le=365),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: EventQueryHandler = Depends(get_event_query_handler),
    role: ClanRole = RequireViewer,
    include: str | None = Query(None),
) -> dict[str, Any]:
    """Get upcoming events within the next N days.

    ``today`` is computed HERE, in the platform timezone (Finding 3, pre-merge
    review) — not left to the handler's server-local ``date.today()`` fallback —
    so the "is it N days away" gate can't disagree with the platform's actual
    calendar day just because the container runs in a different system timezone.
    """
    today = datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE)).date()
    upcoming = await query_handler.get_upcoming(clan_id=clan_id, days=days, today=today)

    includes = {item.strip() for item in include.split(",")} if include else set()
    if "person" in includes:
        for item in upcoming:
            if item.get("person_id") and item.get("person_name"):
                item["person"] = {
                    "id": item["person_id"],
                    "full_name": item["person_name"],
                    "avatar_url": item.get("person_avatar_url"),
                }
            else:
                item["person"] = None

    return {"data": upcoming}


@router.get("/{event_id}")
async def get_event(
    event_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    query_handler: EventQueryHandler = Depends(get_event_query_handler),
    person_handler: PersonQueryHandler = Depends(get_person_query_handler),
    role: ClanRole = RequireViewer,
    include: str | None = Query(None),
    fields: str | None = Query(None),
) -> dict[str, Any]:
    event = await query_handler.get(event_id=event_id, clan_id=clan_id)
    data = event.model_dump()

    if include:
        includes = {i.strip() for i in include.split(",")}
        if "person" in includes and event.person_id:
            data["person"] = await _included_person(person_handler, event.person_id, clan_id)

    if fields:
        field_set = {f.strip() for f in fields.split(",")}
        if include:
            field_set.update({i.strip() for i in include.split(",")})
        data = {k: v for k, v in data.items() if k in field_set}

    return {"data": data}


@router.patch("/{event_id}")
async def update_event(
    event_id: uuid.UUID,
    body: EventUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: EventCommandHandler = Depends(get_event_command_handler),
    role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    event = await cmd_handler.update(
        event_id=event_id,
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, role.value),
        changes=changes,
    )
    return {"data": event.model_dump()}


@router.delete("/{event_id}")
async def delete_event(
    event_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    cmd_handler: EventCommandHandler = Depends(get_event_command_handler),
    role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    await cmd_handler.delete(
        event_id=event_id,
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, role.value),
    )
    return {"data": {"message": t("event.deleted"), "id": str(event_id)}}
