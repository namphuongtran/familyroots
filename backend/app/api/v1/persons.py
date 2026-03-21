"""Persons API routes — thin controller delegating to use-case handlers.

CRUD and search operations use the DDD Person bounded context.
Sub-resource endpoints (marriages, parent-child, documents, events, timeline)
remain DB-direct until their respective bounded contexts are migrated.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.person.commands import (
    CreatePerson,
    DeletePerson,
    GetPerson,
    ListPersons,
    RestorePerson,
    SearchPersons,
    UpdatePerson,
)
from app.application.person.handlers import PersonCommandHandler, PersonQueryHandler
from app.core.database import get_db
from app.core.permissions import ClanRole, RequireAdmin, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.dependencies import get_person_command_handler, get_person_query_handler
from app.models.document import Document
from app.models.event import Event
from app.models.marriage import Marriage
from app.models.parent_child import ParentChild
from app.schemas.auth import UserProfile
from app.schemas.claim import IdentityClaimResponse, IdentityClaimSubmit
from app.schemas.event import TimelineEvent
from app.schemas.person import PersonCreateRequest, PersonUpdateRequest
from app.services.translator import t
from app.application.person.claim_handlers import ClaimCommandHandler

router = APIRouter()


# ── List / Search ──────────────────────────────────────────────


@router.get("")
async def list_persons(
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    _role: ClanRole = RequireViewer,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    generation: int | None = None,
    gender: str | None = None,
    is_alive: bool | None = None,
) -> dict[str, Any]:
    """List persons belonging to a clan with pagination."""
    persons, total = await handler.list(
        ListPersons(
            clan_id=clan_id,
            gender=gender,
            generation=generation,
            cursor=cursor,
            limit=limit,
        )
    )
    return {
        "data": [
            {
                "id": str(p.id),
                "full_name": p.full_name,
                "gender": p.gender,
                "birth_date": p.birth_date.isoformat() if p.birth_date else None,
                "death_date": p.death_date.isoformat() if p.death_date else None,
                "avatar_url": p.avatar_url,
            }
            for p in persons
        ],
        "total": total,
    }


@router.get("/search")
async def search_persons(
    q: str = Query(..., min_length=1),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    _role: ClanRole = RequireViewer,
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    """Fuzzy search persons in a clan by name."""
    results = await handler.search(SearchPersons(clan_id=clan_id, query=q, limit=limit))
    return {
        "data": [
            {
                "id": str(r.id),
                "full_name": r.full_name,
                "gender": r.gender,
                "birth_date": r.birth_date.isoformat() if r.birth_date else None,
                "avatar_url": r.avatar_url,
                "generation": r.generation,
            }
            for r in results
        ]
    }


# ── CRUD ──────────────────────────────────────────────────────


@router.post("", status_code=201)
async def create_person(
    body: PersonCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonCommandHandler = Depends(get_person_command_handler),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a new person and add a clan membership."""
    person = await handler.create(
        CreatePerson(
            actor=ActorInfo.from_jwt(current_user, "editor"),
            clan_id=clan_id,
            created_by_clan_id=body.created_by_clan_id or clan_id,
            **body.model_dump(exclude={"created_by_clan_id"}),
        )
    )
    return {"data": person.model_dump()}


@router.get("/{person_id}")
async def get_person(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get a single person's full detail."""
    person = await handler.get(GetPerson(person_id=person_id, clan_id=clan_id))
    return {"data": person.model_dump()}


@router.patch("/{person_id}")
async def update_person(
    person_id: uuid.UUID,
    body: PersonUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonCommandHandler = Depends(get_person_command_handler),
    user_role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Update a person's details."""
    person = await handler.update(
        UpdatePerson(
            person_id=person_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, user_role.value),
            changes=body.model_dump(exclude_unset=True),
        )
    )
    return {"data": person.model_dump()}


@router.delete("/{person_id}")
async def delete_person(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonCommandHandler = Depends(get_person_command_handler),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Soft-delete a person (admin only)."""
    await handler.delete(
        DeletePerson(
            person_id=person_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, "admin"),
        )
    )
    return {"data": {"message": t("person.deleted"), "id": str(person_id)}}


@router.post("/{person_id}/restore")
async def restore_person(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonCommandHandler = Depends(get_person_command_handler),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Restore a soft-deleted person (admin only)."""
    await handler.restore(
        RestorePerson(
            person_id=person_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, "admin"),
        )
    )
    return {"data": {"message": t("person.restored"), "id": str(person_id)}}


@router.post("/{person_id}/claim", response_model=IdentityClaimResponse, status_code=201)
async def submit_identity_claim(
    person_id: uuid.UUID,
    body: IdentityClaimSubmit,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> IdentityClaimResponse:
    """Submit a claim for linking a user profile to a person in the family tree."""
    user_id = uuid.UUID(current_user["sub"])
    handler = ClaimCommandHandler(db)
    return await handler.submit_claim(
        user_id=user_id,
        person_id=person_id,
        requester_note=body.requester_note,
    )


# ── Sub-resources (kept DB-direct until later phases migrate) ─


@router.get("/{person_id}/marriages")
async def person_marriages(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get all marriages for a person."""
    await handler.get(GetPerson(person_id=person_id, clan_id=clan_id))
    from app.schemas.marriage import MarriageResponse

    result = await db.execute(
        select(Marriage).where(
            or_(Marriage.person1_id == person_id, Marriage.person2_id == person_id),
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
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get all parent-child relationships for a person."""
    await handler.get(GetPerson(person_id=person_id, clan_id=clan_id))
    from app.schemas.parent_child import ParentChildResponse

    result = await db.execute(
        select(ParentChild).where(
            or_(ParentChild.parent_id == person_id, ParentChild.child_id == person_id),
            ParentChild.is_deleted.is_(False),
        )
    )
    links = result.scalars().all()
    return {"data": [ParentChildResponse.model_validate(link).model_dump() for link in links]}


@router.get("/{person_id}/documents")
async def person_documents(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get all documents for a person."""
    await handler.get(GetPerson(person_id=person_id, clan_id=clan_id))
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
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get all events for a person."""
    await handler.get(GetPerson(person_id=person_id, clan_id=clan_id))
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
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Return a chronological timeline of life events for a person."""
    person = await handler.get(GetPerson(person_id=person_id, clan_id=clan_id))
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

    # Marriages (raw SQL stays until Relationship context migrated)
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
