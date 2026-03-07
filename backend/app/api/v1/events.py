"""Events API routes — death anniversaries, birthdays, clan events."""

import uuid
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.core.pagination import build_page, paginate_query
from app.core.permissions import ClanRole, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.models.audit_log import AuditLog
from app.models.event import Event
from app.models.member import Member
from app.schemas.event import EventCreateRequest, EventResponse, EventUpdateRequest

router = APIRouter()


@router.post("", status_code=201)
async def create_event(
    body: EventCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a new event (death anniversary, birthday, etc.)."""
    actor_id = uuid.UUID(current_user["sub"])

    # Verify member belongs to clan if provided
    if body.member_id:
        result = await db.execute(
            select(Member).where(
                Member.id == body.member_id,
                Member.clan_id == clan_id,
                Member.is_deleted.is_(False),
            )
        )
        if not result.scalar_one_or_none():
            raise NotFoundError("member_not_found")

    event = Event(
        clan_id=clan_id,
        member_id=body.member_id,
        event_type=body.event_type,
        title=body.title,
        description=body.description,
        event_date=body.event_date,
        is_lunar_calendar=body.is_lunar_calendar,
        is_recurring=body.is_recurring,
        notify_days_before=body.notify_days_before,
        created_by=actor_id,
    )
    db.add(event)
    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=actor_id,
            actor_role="editor",
            action="event.create",
            resource_type="event",
            resource_id=event.id,
        )
    )
    await db.commit()
    await db.refresh(event)
    return {"data": EventResponse.model_validate(event).model_dump()}


@router.get("")
async def list_events(
    member_id: uuid.UUID | None = Query(None),
    event_type: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """List events with optional filters."""
    query = select(Event).where(Event.clan_id == clan_id)
    if member_id:
        query = query.where(Event.member_id == member_id)
    if event_type:
        query = query.where(Event.event_type == event_type)

    query = paginate_query(query, Event, cursor, limit)
    result = await db.execute(query)
    events = list(result.scalars().all())

    page = build_page(events, limit)
    page["data"] = [EventResponse.model_validate(e).model_dump() for e in page["data"]]
    return page


@router.get("/upcoming")
async def get_upcoming_events(
    days: int = Query(30, ge=1, le=365),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get upcoming events within the next N days.

    For recurring events, compute the next occurrence using
    MAKE_DATE with the current year.
    """
    today = date.today()
    end_date = today + timedelta(days=days)

    result = await db.execute(
        text(
            "SELECT e.id, e.member_id, e.event_type, e.title, e.event_date, "
            "  e.is_lunar_calendar, e.is_recurring, "
            "  m.full_name AS member_name, m.avatar_url AS member_avatar_url, "
            "  CASE "
            "    WHEN e.is_recurring THEN "
            "      CASE "
            "        WHEN MAKE_DATE(EXTRACT(YEAR FROM CURRENT_DATE)::int, "
            "             EXTRACT(MONTH FROM e.event_date)::int, "
            "             EXTRACT(DAY FROM e.event_date)::int) >= CURRENT_DATE "
            "        THEN MAKE_DATE(EXTRACT(YEAR FROM CURRENT_DATE)::int, "
            "             EXTRACT(MONTH FROM e.event_date)::int, "
            "             EXTRACT(DAY FROM e.event_date)::int) "
            "        ELSE MAKE_DATE(EXTRACT(YEAR FROM CURRENT_DATE)::int + 1, "
            "             EXTRACT(MONTH FROM e.event_date)::int, "
            "             EXTRACT(DAY FROM e.event_date)::int) "
            "      END "
            "    ELSE e.event_date "
            "  END AS next_occurrence "
            "FROM public.events e "
            "LEFT JOIN public.members m ON m.id = e.member_id "
            "WHERE e.clan_id = :clan_id "
            "  AND ("
            "    (e.is_recurring = true) OR "
            "    (e.is_recurring = false AND e.event_date >= :today)"
            "  ) "
            "HAVING CASE "
            "  WHEN e.is_recurring THEN "
            "    CASE "
            "      WHEN MAKE_DATE(EXTRACT(YEAR FROM CURRENT_DATE)::int, "
            "           EXTRACT(MONTH FROM e.event_date)::int, "
            "           EXTRACT(DAY FROM e.event_date)::int) >= CURRENT_DATE "
            "      THEN MAKE_DATE(EXTRACT(YEAR FROM CURRENT_DATE)::int, "
            "           EXTRACT(MONTH FROM e.event_date)::int, "
            "           EXTRACT(DAY FROM e.event_date)::int) "
            "      ELSE MAKE_DATE(EXTRACT(YEAR FROM CURRENT_DATE)::int + 1, "
            "           EXTRACT(MONTH FROM e.event_date)::int, "
            "           EXTRACT(DAY FROM e.event_date)::int) "
            "    END "
            "  ELSE e.event_date "
            "END BETWEEN :today AND :end_date "
            "ORDER BY next_occurrence ASC "
            "LIMIT 50"
        ),
        {"clan_id": clan_id, "today": today, "end_date": end_date},
    )
    rows = result.mappings().all()

    upcoming = []
    for row in rows:
        next_occ = row["next_occurrence"]
        upcoming.append(
            {
                "id": str(row["id"]),
                "member_id": str(row["member_id"]) if row["member_id"] else None,
                "member_name": row["member_name"],
                "member_avatar_url": row["member_avatar_url"],
                "event_type": row["event_type"],
                "title": row["title"],
                "event_date": row["event_date"].isoformat(),
                "next_occurrence": next_occ.isoformat() if next_occ else None,
                "days_until": (next_occ - today).days if next_occ else None,
                "is_lunar_calendar": row["is_lunar_calendar"],
            }
        )
    return {"data": upcoming}


@router.get("/{event_id}")
async def get_event(
    event_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    event = await _get_event_or_404(event_id, clan_id, db)
    return {"data": EventResponse.model_validate(event).model_dump()}


@router.patch("/{event_id}")
async def update_event(
    event_id: uuid.UUID,
    body: EventUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    event = await _get_event_or_404(event_id, clan_id, db)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(event, field, value)

    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=uuid.UUID(current_user["sub"]),
            actor_role="editor",
            action="event.update",
            resource_type="event",
            resource_id=event.id,
        )
    )
    await db.commit()
    await db.refresh(event)
    return {"data": EventResponse.model_validate(event).model_dump()}


@router.delete("/{event_id}")
async def delete_event(
    event_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    event = await _get_event_or_404(event_id, clan_id, db)

    await db.delete(event)
    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=uuid.UUID(current_user["sub"]),
            actor_role="editor",
            action="event.delete",
            resource_type="event",
            resource_id=event_id,
        )
    )
    await db.commit()
    return {"data": {"message": "Event deleted", "id": str(event_id)}}


async def _get_event_or_404(event_id: uuid.UUID, clan_id: uuid.UUID, db: AsyncSession) -> Event:
    result = await db.execute(select(Event).where(Event.id == event_id, Event.clan_id == clan_id))
    event = result.scalar_one_or_none()
    if not event:
        raise NotFoundError("event_not_found")
    return event
