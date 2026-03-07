"""Members API routes — CRUD, search, timeline, sub-resource endpoints."""

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
from app.models.document import Document
from app.models.event import Event
from app.models.member import Member
from app.models.relationship import Relationship
from app.schemas.event import TimelineEvent
from app.schemas.member import MemberCreateRequest, MemberResponse, MemberUpdateRequest
from app.services.translator import t

router = APIRouter()


# ── List / Search ──────────────────────────────────────────────


@router.get("")
async def list_members(
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
    """List clan members with cursor pagination and optional filters."""
    query = select(Member).where(Member.clan_id == clan_id, Member.is_deleted.is_(False))
    if generation is not None:
        query = query.where(Member.generation == generation)
    if gender is not None:
        query = query.where(Member.gender == gender)
    if is_alive is True:
        query = query.where(Member.death_date.is_(None))
    elif is_alive is False:
        query = query.where(Member.death_date.isnot(None))

    query = paginate_query(query, Member, cursor, limit)
    result = await db.execute(query)
    items = list(result.scalars().all())
    page = build_page(items, limit)
    page["data"] = [
        {
            "id": str(m.id),
            "full_name": m.full_name,
            "gender": m.gender,
            "birth_date": m.birth_date.isoformat() if m.birth_date else None,
            "death_date": m.death_date.isoformat() if m.death_date else None,
            "avatar_url": m.avatar_url,
            "generation": m.generation,
        }
        for m in page["data"]
    ]
    return page


@router.get("/search")
async def search_members(
    q: str = Query(..., min_length=1),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    """Fuzzy search members by name using PostgreSQL trigram + unaccent."""
    result = await db.execute(
        text("""
            SELECT id, full_name, gender, birth_date, death_date,
                   avatar_url, generation
            FROM public.members
            WHERE clan_id = :clan_id
              AND is_deleted = false
              AND (
                public.f_unaccent(full_name) ILIKE public.f_unaccent('%' || :q || '%')
                OR similarity(public.f_unaccent(full_name), public.f_unaccent(:q)) > 0.3
              )
            ORDER BY similarity(public.f_unaccent(full_name), public.f_unaccent(:q)) DESC
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
async def create_member(
    body: MemberCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a new family member."""
    actor_id = uuid.UUID(current_user["sub"])
    member = Member(
        **body.model_dump(),
        clan_id=clan_id,
        created_by=actor_id,
    )
    db.add(member)
    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=actor_id,
            actor_role="editor",
            action="member.create",
            resource_type="member",
            resource_id=member.id,
        )
    )
    await db.commit()
    await db.refresh(member)
    return {"data": MemberResponse.model_validate(member).model_dump()}


@router.get("/{member_id}")
async def get_member(
    member_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get a single member's full detail."""
    member = await _get_member_or_404(member_id, clan_id, db)
    return {"data": MemberResponse.model_validate(member).model_dump()}


@router.patch("/{member_id}")
async def update_member(
    member_id: uuid.UUID,
    body: MemberUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Update a member's details."""
    member = await _get_member_or_404(member_id, clan_id, db)
    actor_id = uuid.UUID(current_user["sub"])

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(member, field, value)
    member.updated_by = actor_id

    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=actor_id,
            actor_role="editor",
            action="member.update",
            resource_type="member",
            resource_id=member.id,
            new_value=update_data,
        )
    )
    await db.commit()
    await db.refresh(member)
    return {"data": MemberResponse.model_validate(member).model_dump()}


@router.delete("/{member_id}")
async def delete_member(
    member_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Soft-delete a member (admin only)."""
    member = await _get_member_or_404(member_id, clan_id, db)
    actor_id = uuid.UUID(current_user["sub"])

    member.is_deleted = True
    member.deleted_at = datetime.now(UTC)
    member.deleted_by = actor_id

    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=actor_id,
            actor_role="admin",
            action="member.delete",
            resource_type="member",
            resource_id=member.id,
        )
    )
    await db.commit()
    return {"data": {"message": t("member.deleted"), "id": str(member_id)}}


@router.post("/{member_id}/restore")
async def restore_member(
    member_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Restore a soft-deleted member (admin only)."""
    result = await db.execute(
        select(Member).where(
            Member.id == member_id,
            Member.clan_id == clan_id,
            Member.is_deleted.is_(True),
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise NotFoundError("member_not_found")

    member.is_deleted = False
    member.deleted_at = None
    member.deleted_by = None

    db.add(
        AuditLog(
            clan_id=clan_id,
            actor_id=uuid.UUID(current_user["sub"]),
            actor_role="admin",
            action="member.restore",
            resource_type="member",
            resource_id=member.id,
        )
    )
    await db.commit()
    return {"data": {"message": t("member.restored"), "id": str(member_id)}}


# ── Sub-resources ─────────────────────────────────────────────


@router.get("/{member_id}/relationships")
async def member_relationships(
    member_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get all relationships for a member."""
    await _get_member_or_404(member_id, clan_id, db)
    result = await db.execute(
        select(Relationship).where(
            Relationship.clan_id == clan_id,
            or_(
                Relationship.member_id == member_id,
                Relationship.related_id == member_id,
            ),
        )
    )
    rels = result.scalars().all()
    from app.schemas.relationship import RelationshipResponse

    return {"data": [RelationshipResponse.model_validate(r).model_dump() for r in rels]}


@router.get("/{member_id}/documents")
async def member_documents(
    member_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get all documents for a member."""
    await _get_member_or_404(member_id, clan_id, db)
    result = await db.execute(
        select(Document).where(Document.clan_id == clan_id, Document.member_id == member_id)
    )
    docs = result.scalars().all()
    from app.schemas.document import DocumentSummary

    return {"data": [DocumentSummary.model_validate(d).model_dump() for d in docs]}


@router.get("/{member_id}/events")
async def member_events(
    member_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Get all events for a member."""
    await _get_member_or_404(member_id, clan_id, db)
    result = await db.execute(
        select(Event).where(Event.clan_id == clan_id, Event.member_id == member_id)
    )
    events = result.scalars().all()
    from app.schemas.event import EventResponse

    return {"data": [EventResponse.model_validate(e).model_dump() for e in events]}


@router.get("/{member_id}/timeline")
async def member_timeline(
    member_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    db: AsyncSession = Depends(get_db),
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Return a chronological timeline of life events for a member."""
    member = await _get_member_or_404(member_id, clan_id, db)
    timeline: list[dict[str, Any]] = []

    # Birth
    if member.birth_date:
        timeline.append(
            TimelineEvent(
                date=member.birth_date,
                date_approx=member.birth_date_approx,
                event_type="birth",
                title=t("timeline.birth"),
            ).model_dump()
        )

    # Death
    if member.death_date:
        timeline.append(
            TimelineEvent(
                date=member.death_date,
                date_approx=member.death_date_approx,
                event_type="death",
                title=t("timeline.death"),
            ).model_dump()
        )

    # Marriages
    spouse_result = await db.execute(
        text("""
            SELECT r.start_date, r.end_date, r.relation_subtype,
                   CASE WHEN r.member_id = :mid THEN r.related_id ELSE r.member_id END AS spouse_id,
                   m.full_name AS spouse_name
            FROM public.relationships r
            JOIN public.members m
              ON m.id = CASE WHEN r.member_id = :mid
                             THEN r.related_id ELSE r.member_id END
            WHERE r.clan_id = :clan_id
              AND r.relation_type = 'spouse'
              AND (r.member_id = :mid OR r.related_id = :mid)
        """),
        {"mid": member_id, "clan_id": clan_id},
    )
    for row in spouse_result.mappings().all():
        timeline.append(
            TimelineEvent(
                date=row["start_date"],
                date_approx=False,
                event_type="marriage",
                title=t("timeline.marriage"),
                related_member_id=row["spouse_id"],
                related_member_name=row["spouse_name"],
            ).model_dump()
        )

    # Custom events
    events_result = await db.execute(
        select(Event).where(Event.clan_id == clan_id, Event.member_id == member_id)
    )
    for ev in events_result.scalars().all():
        timeline.append(
            TimelineEvent(
                date=ev.event_date,
                date_approx=False,
                event_type=ev.event_type,
                title=ev.title,
                description=ev.description,
            ).model_dump()
        )

    # Sort chronologically (None dates last)
    timeline.sort(key=lambda e: e.get("date") or "9999-12-31")

    return {"data": timeline}


# ── Helpers ───────────────────────────────────────────────────


async def _get_member_or_404(member_id: uuid.UUID, clan_id: uuid.UUID, db: AsyncSession) -> Member:
    result = await db.execute(
        select(Member).where(
            Member.id == member_id,
            Member.clan_id == clan_id,
            Member.is_deleted.is_(False),
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise NotFoundError("member_not_found")
    return member
