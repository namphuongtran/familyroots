"""Persons API routes — CRUD, search, timeline, sub-resource endpoints."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.core.pagination import build_page, paginate_query
from app.core.permissions import ClanRole, RequireAdmin, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.models.audit_log import AuditLog
from app.models.clan_membership import ClanMembership
from app.models.document import Document
from app.models.event import Event
from app.models.marriage import Marriage
from app.models.parent_child import ParentChild
from app.models.person import Person
from app.schemas.event import TimelineEvent
from app.schemas.person import PersonCreateRequest, PersonResponse, PersonUpdateRequest
from app.services.translator import t

router = APIRouter()


# ── List / Search ──────────────────────────────────────────────


@router.get("")
async def list_persons(
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    generation: int | None = None,
    gender: str | None = None,
    is_alive: bool | None = None,
) -> dict[str, Any]:
    """List persons belonging to a clan (via clan_memberships) with pagination."""
    query = (
        select(Person)
        .join(ClanMembership, ClanMembership.person_id == Person.id)
        .where(ClanMembership.clan_id == clan_id, Person.is_deleted.is_(False))
    )
    if generation is not None:
        query = query.where(ClanMembership.generation == generation)
    if gender is not None:
        query = query.where(Person.gender == gender)
    if is_alive is True:
        query = query.where(Person.death_date.is_(None))
    elif is_alive is False:
        query = query.where(Person.death_date.isnot(None))

    query = paginate_query(query, Person, cursor, limit)
    result = await db.execute(query)
    items = list(result.scalars().all())
    page = build_page(items, limit)
    page["data"] = [
        {
            "id": str(p.id),
            "full_name": p.full_name,
            "gender": p.gender,
            "birth_date": p.birth_date.isoformat() if p.birth_date else None,
            "death_date": p.death_date.isoformat() if p.death_date else None,
            "avatar_url": p.avatar_url,
        }
        for p in page["data"]
    ]
    return page


@router.get("/search")
async def search_persons(
    q: str = Query(..., min_length=1),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    """Fuzzy search persons in a clan by name using PostgreSQL trigram + unaccent."""
    result = await db.execute(
        text("""
            SELECT p.id, p.full_name, p.gender, p.birth_date, p.death_date,
                   p.avatar_url, cm.generation
            FROM public.persons p
            JOIN public.clan_memberships cm ON cm.person_id = p.id
            WHERE cm.clan_id = :clan_id
              AND p.is_deleted = false
              AND (
                public.f_unaccent(p.full_name) ILIKE public.f_unaccent('%' || :q || '%')
                OR similarity(public.f_unaccent(p.full_name), public.f_unaccent(:q)) > 0.3
              )
            ORDER BY similarity(public.f_unaccent(p.full_name), public.f_unaccent(:q)) DESC
            LIMIT :limit
        """),
        {"clan_id": clan_id, "q": q, "limit": limit},
    )
    rows = result.mappings().all()
    return {
        "data": [
            {
                "id": str(r["id"]),
                "full_name": r["full_name"],
                "gender": r["gender"],
                "birth_date": r["birth_date"].isoformat() if r["birth_date"] else None,
                "death_date": r["death_date"].isoformat() if r["death_date"] else None,
                "avatar_url": r["avatar_url"],
                "generation": r["generation"],
            }
            for r in rows
        ]
    }


# ── CRUD ──────────────────────────────────────────────────────


@router.post("", status_code=201)
async def create_person(
    body: PersonCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a new person and add a clan membership."""
    actor_id = uuid.UUID(current_user["sub"])
    person = Person(
        **body.model_dump(exclude={"origin_clan_id"}),
        origin_clan_id=body.origin_clan_id or clan_id,
        created_by=actor_id,
    )
    db.add(person)
    # Auto-create clan membership for the creating clan
    membership = ClanMembership(
        person_id=person.id,
        clan_id=clan_id,
        role="blood",
    )
    db.add(membership)
    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=actor_id,
            actor_role="editor",
            action="person.create",
            resource_type="person",
            resource_id=person.id,
        )
    )
    await db.commit()
    await db.refresh(person)
    return {"data": PersonResponse.model_validate(person).model_dump()}


@router.get("/{person_id}")
async def get_person(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get a single person's full detail."""
    person = await _get_person_or_404(person_id, clan_id, db)
    return {"data": PersonResponse.model_validate(person).model_dump()}


@router.patch("/{person_id}")
async def update_person(
    person_id: uuid.UUID,
    body: PersonUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Update a person's details."""
    person = await _get_person_or_404(person_id, clan_id, db)
    actor_id = uuid.UUID(current_user["sub"])

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(person, field, value)
    person.updated_by = actor_id

    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=actor_id,
            actor_role="editor",
            action="person.update",
            resource_type="person",
            resource_id=person.id,
            new_value=update_data,
        )
    )
    await db.commit()
    await db.refresh(person)
    return {"data": PersonResponse.model_validate(person).model_dump()}


@router.delete("/{person_id}")
async def delete_person(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Soft-delete a person (admin only)."""
    person = await _get_person_or_404(person_id, clan_id, db)
    actor_id = uuid.UUID(current_user["sub"])

    person.is_deleted = True
    person.deleted_at = datetime.now(UTC)
    person.deleted_by = actor_id

    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=actor_id,
            actor_role="admin",
            action="person.delete",
            resource_type="person",
            resource_id=person.id,
        )
    )
    await db.commit()
    return {"data": {"message": t("person.deleted"), "id": str(person_id)}}


@router.post("/{person_id}/restore")
async def restore_person(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Restore a soft-deleted person (admin only)."""
    result = await db.execute(
        select(Person)
        .join(ClanMembership, ClanMembership.person_id == Person.id)
        .where(
            Person.id == person_id,
            ClanMembership.clan_id == clan_id,
            Person.is_deleted.is_(True),
        )
    )
    person = result.scalar_one_or_none()
    if not person:
        raise NotFoundError("person_not_found")

    person.is_deleted = False
    person.deleted_at = None
    person.deleted_by = None

    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=uuid.UUID(current_user["sub"]),
            actor_role="admin",
            action="person.restore",
            resource_type="person",
            resource_id=person.id,
        )
    )
    await db.commit()
    return {"data": {"message": t("person.restored"), "id": str(person_id)}}


# ── Sub-resources ─────────────────────────────────────────────


@router.get("/{person_id}/marriages")
async def person_marriages(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get all marriages for a person."""
    await _get_person_or_404(person_id, clan_id, db)
    from app.schemas.marriage import MarriageResponse

    result = await db.execute(
        select(Marriage).where(
            or_(
                Marriage.person1_id == person_id,
                Marriage.person2_id == person_id,
            ),
            Marriage.is_deleted.is_(False),
        )
    )
    marriages = result.scalars().all()
    return {"data": [MarriageResponse.model_validate(m).model_dump() for m in marriages]}


@router.get("/{person_id}/parent-child")
async def person_parent_child(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get all parent-child relationships for a person."""
    await _get_person_or_404(person_id, clan_id, db)
    from app.schemas.parent_child import ParentChildResponse

    result = await db.execute(
        select(ParentChild).where(
            or_(
                ParentChild.parent_id == person_id,
                ParentChild.child_id == person_id,
            ),
            ParentChild.is_deleted.is_(False),
        )
    )
    links = result.scalars().all()
    return {"data": [ParentChildResponse.model_validate(l).model_dump() for l in links]}


@router.get("/{person_id}/documents")
async def person_documents(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get all documents for a person."""
    await _get_person_or_404(person_id, clan_id, db)
    result = await db.execute(
        select(Document).where(Document.clan_id == clan_id, Document.person_id == person_id)
    )
    docs = result.scalars().all()
    from app.schemas.document import DocumentSummary

    return {"data": [DocumentSummary.model_validate(d).model_dump() for d in docs]}


@router.get("/{person_id}/events")
async def person_events(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get all events for a person."""
    await _get_person_or_404(person_id, clan_id, db)
    result = await db.execute(
        select(Event).where(Event.clan_id == clan_id, Event.person_id == person_id)
    )
    events = result.scalars().all()
    from app.schemas.event import EventResponse

    return {"data": [EventResponse.model_validate(e).model_dump() for e in events]}


@router.get("/{person_id}/timeline")
async def person_timeline(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Return a chronological timeline of life events for a person."""
    person = await _get_person_or_404(person_id, clan_id, db)
    timeline: list[dict[str, Any]] = []

    # Birth
    if person.birth_date:
        timeline.append(
            TimelineEvent(
                event_date=person.birth_date,
                date_approx=person.birth_date_approx,
                event_type="birth",
                title=t("timeline.birth"),
            ).model_dump()
        )

    # Death
    if person.death_date:
        timeline.append(
            TimelineEvent(
                event_date=person.death_date,
                date_approx=person.death_date_approx,
                event_type="death",
                title=t("timeline.death"),
            ).model_dump()
        )

    # Marriages
    spouse_result = await db.execute(
        text("""
            SELECT m.marriage_date, m.divorce_date, m.status,
                   CASE WHEN m.person1_id = :pid THEN m.person2_id
                        ELSE m.person1_id END AS spouse_id,
                   p.full_name AS spouse_name
            FROM public.marriages m
            JOIN public.persons p
              ON p.id = CASE WHEN m.person1_id = :pid
                             THEN m.person2_id ELSE m.person1_id END
            WHERE (m.person1_id = :pid OR m.person2_id = :pid)
              AND m.is_deleted = false
        """),
        {"pid": person_id},
    )
    for row in spouse_result.mappings().all():
        timeline.append(
            TimelineEvent(
                event_date=row["marriage_date"],
                date_approx=False,
                event_type="marriage",
                title=t("timeline.marriage"),
                related_person_id=row["spouse_id"],
                related_person_name=row["spouse_name"],
            ).model_dump()
        )

    # Custom events
    events_result = await db.execute(
        select(Event).where(Event.clan_id == clan_id, Event.person_id == person_id)
    )
    for ev in events_result.scalars().all():
        timeline.append(
            TimelineEvent(
                event_date=ev.event_date,
                date_approx=False,
                event_type=ev.event_type,
                title=ev.title,
                description=ev.description,
            ).model_dump()
        )

    # Sort chronologically (None dates last)
    timeline.sort(key=lambda e: e.get("event_date") or "9999-12-31")

    return {"data": timeline}


# ── Helpers ───────────────────────────────────────────────────


async def _get_person_or_404(
    person_id: uuid.UUID, clan_id: uuid.UUID, db: AsyncSession
) -> Person:
    result = await db.execute(
        select(Person)
        .join(ClanMembership, ClanMembership.person_id == Person.id)
        .where(
            Person.id == person_id,
            ClanMembership.clan_id == clan_id,
            Person.is_deleted.is_(False),
        )
    )
    person = result.scalar_one_or_none()
    if not person:
        raise NotFoundError("person_not_found")
    return person
