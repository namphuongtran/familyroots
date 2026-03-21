"""Events API routes — thin controller delegating to Event handlers."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.event.handlers import EventCommandHandler, EventQueryHandler
from app.core.database import get_db
from app.core.permissions import ClanRole, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.value_objects import ActorInfo
from app.schemas.event import EventCreateRequest, EventUpdateRequest

router = APIRouter()


def _make_handlers(db: AsyncSession) -> tuple[EventCommandHandler, EventQueryHandler]:
    from app.infrastructure.event_dispatcher import create_event_dispatcher
    from app.infrastructure.persistence.event_repository import SqlAlchemyEventRepository
    from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

    repo = SqlAlchemyEventRepository(db)
    dispatcher = create_event_dispatcher(db)
    uow = SqlAlchemyUnitOfWork(db, dispatcher)
    return EventCommandHandler(repo, uow), EventQueryHandler(repo)


@router.post("", status_code=201)
async def create_event(
    body: EventCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a new event."""
    cmd_handler, _ = _make_handlers(db)
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
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """List events with optional filters."""
    _, query_handler = _make_handlers(db)
    items = await query_handler.list_events(
        clan_id=clan_id, person_id=person_id, event_type=event_type,
        cursor=cursor, limit=limit,
    )
    return {"data": [item.model_dump() for item in items]}


@router.get("/upcoming")
async def get_upcoming_events(
    days: int = Query(30, ge=1, le=365),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get upcoming events within the next N days."""
    _, query_handler = _make_handlers(db)
    upcoming = await query_handler.get_upcoming(clan_id=clan_id, days=days)
    return {"data": upcoming}


@router.get("/{event_id}")
async def get_event(
    event_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    _, query_handler = _make_handlers(db)
    event = await query_handler.get(event_id=event_id, clan_id=clan_id)
    return {"data": event.model_dump()}


@router.patch("/{event_id}")
async def update_event(
    event_id: uuid.UUID,
    body: EventUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    cmd_handler, _ = _make_handlers(db)
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
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    cmd_handler, _ = _make_handlers(db)
    await cmd_handler.delete(
        event_id=event_id,
        clan_id=clan_id,
        actor=ActorInfo.from_jwt(current_user, "editor"),
    )
    return {"data": {"message": "Event deleted", "id": str(event_id)}}
