"""Persons API routes — thin controller delegating to use-case handlers.

CRUD and search operations use the DDD Person bounded context.
Sub-resource endpoints (marriages, parent-child, documents, events, timeline)
remain DB-direct until their respective bounded contexts are migrated.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.application.person.claim_handlers import ClaimCommandHandler
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
from app.core.fieldsets import filter_dict, filter_list, parse_field_set, parse_includes
from app.core.permissions import ClanRole, RequireAdmin, RequireEditor, RequireViewer
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.dependencies import (
    get_claim_command_handler,
    get_person_command_handler,
    get_person_query_handler,
)
from app.schemas.claim import IdentityClaimSubmit
from app.schemas.envelope import created, ok, ok_message, page
from app.schemas.historical_date import to_historical_date
from app.schemas.person import (
    PersonBatchGetRequest,
    PersonCreateRequest,
    PersonDetail,
    PersonResponse,
    PersonSummary,
    PersonUpdateRequest,
)
from app.services.translator import t

router = APIRouter()


def _serialize_person_by_profile(person: Any, profile: str) -> dict[str, Any]:
    """Serialize a person to the selected response profile.

    Full dumps (not exclude_unset) so every declared key of the chosen profile
    is always present — key presence must not vary with which fields were set.
    """
    if profile == "summary":
        return PersonSummary.model_validate(person).model_dump()
    if profile == "detail":
        return PersonDetail.model_validate(person).model_dump()
    dumped: dict[str, Any] = person.model_dump()
    return dumped


def _dedupe_person_ids(ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Return IDs with original order preserved and duplicates removed."""
    return list(dict.fromkeys(ids))


def _parse_include_by_id(
    include_by_id: dict[uuid.UUID, str] | None,
) -> dict[uuid.UUID, list[str]]:
    """Parse per-person include values into normalized include lists."""
    if not include_by_id:
        return {}
    return {
        uuid.UUID(str(person_id)): parse_includes(value)
        for person_id, value in include_by_id.items()
    }


# ── List / Search ──────────────────────────────────────────────


@router.get("", responses=page(PersonResponse))
async def list_persons(
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    role: ClanRole = RequireViewer,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    generation: int | None = None,
    gender: str | None = None,
    profile: str = Query(
        "full",
        pattern="^(summary|detail|full)$",
        description=(
            "Response profile. Use summary for list cards, detail for medium "
            "payload, full for all fields."
        ),
    ),
    include: str | None = Query(
        None,
        description="Comma-separated embedded resources. Example: stats",
    ),
    fields: str | None = Query(
        None,
        description="Comma-separated sparse fields. Example: id,full_name,stats",
    ),
) -> dict[str, Any]:
    """List persons belonging to a clan with pagination."""
    persons, meta = await handler.list_persons(
        ListPersons(
            clan_id=clan_id,
            gender=gender,
            generation=generation,
            cursor=cursor,
            limit=limit,
        )
    )
    await handler.redact_pii(
        persons, viewer_role=role.value, viewer_user_id=uuid.UUID(current_user["sub"])
    )

    includes = parse_includes(include)
    include_set = set(includes)
    field_set = parse_field_set(fields, include=include)

    stats_map = {}
    if "stats" in include_set and persons:
        person_ids = [p.id for p in persons]
        stats_map = await handler.get_persons_stats(clan_id, person_ids)

    res_data = []
    for p in persons:
        p_dict = _serialize_person_by_profile(p, profile)

        if "stats" in include_set and p.id in stats_map:
            p_dict["stats"] = stats_map[p.id]

        res_data.append(filter_dict(p_dict, field_set))

    return {
        "data": res_data,
        "meta": meta,
    }


@router.get("/search")
async def search_persons(
    q: str = Query(..., min_length=1),
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    role: ClanRole = RequireViewer,
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
                # Contract: person dates are HistoricalDate objects everywhere,
                # search included; version is the OCC token an edit needs.
                "birth_date": to_historical_date(
                    r.birth_date, r.birth_date_precision, r.birth_date_display, r.lunar_birth_date
                ).model_dump(),
                "avatar_url": r.avatar_url,
                "version": r.version,
                "generation": r.generation,
                "membership_role": r.membership_role,
                "is_founder": r.is_founder,
            }
            for r in results
        ]
    }


# ── CRUD ──────────────────────────────────────────────────────


@router.post("", status_code=201, responses=created(PersonResponse))
async def create_person(
    body: PersonCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonCommandHandler = Depends(get_person_command_handler),
    role: ClanRole = RequireEditor,
) -> dict[str, Any]:
    """Create a new person and add a clan membership."""
    dumped = body.model_dump()
    person = await handler.create(
        CreatePerson(
            actor=ActorInfo.from_jwt(current_user, role.value),
            clan_id=clan_id,
            # Provenance is always the active clan; never client-supplied.
            created_by_clan_id=clan_id,
            **dumped,
        )
    )
    return {"data": person.model_dump()}


async def _fetch_included_data(
    handler: PersonQueryHandler,
    clan_id: uuid.UUID,
    person_id: uuid.UUID,
    includes: list[str],
) -> dict[str, list[Any]]:
    # Sequential awaits, deliberately: everything shares one request-scoped
    # AsyncSession, so a gather adds no real concurrency (a single connection
    # serializes the queries) while risking concurrent-session-use hazards.
    # A failing include sub-query must surface as an error (handled by the
    # app's exception handlers), never be masked as empty data.
    res_dict: dict[str, list[Any]] = {}
    if "marriages" in includes:
        res_dict["marriages"] = await handler.get_marriages(clan_id, person_id)
    if "parent_child" in includes:
        res_dict["parent_child"] = await handler.get_parent_child(clan_id, person_id)
    if "timeline" in includes:
        res_dict["timeline"] = await handler.get_timeline(clan_id, person_id)
    if "documents" in includes:
        res_dict["documents"] = await handler.get_documents(clan_id, person_id)
    return res_dict


def _filter_list_by_fields(items: list[Any], fields: str | None) -> list[Any]:
    return filter_list(items, parse_field_set(fields))


@router.post("/batch")
async def batch_get_persons(
    body: PersonBatchGetRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Fetch multiple persons in one request with optional include/fields/profile.

    Supported include tokens:
    - ``stats`` (spouse_count, child_count)
    - ``marriages``
    - ``parent_child``
    - ``timeline``
    - ``documents``

    ``include`` applies globally. ``include_by_id`` allows per-person overrides.
    Unknown include tokens are ignored for backward compatibility.
    """
    person_ids = _dedupe_person_ids(body.ids)

    # One ANY(:ids) query for the whole batch — never one get() per person
    # (the old gather ran on ONE shared session, so it was N sequential
    # round-trips wearing a concurrency costume).
    persons, missing = await handler.get_many(person_ids, clan_id)
    errors = [{"id": str(pid), "code": "person_not_found"} for pid in missing]

    await handler.redact_pii(
        persons, viewer_role=role.value, viewer_user_id=uuid.UUID(current_user["sub"])
    )

    includes = parse_includes(body.include)
    includes_by_id = _parse_include_by_id(body.include_by_id)
    all_include_keys = set(includes)
    for per_person_includes in includes_by_id.values():
        all_include_keys.update(per_person_includes)
    include_union = ",".join(sorted(all_include_keys)) if all_include_keys else None
    field_set = parse_field_set(body.fields, include=include_union)

    stats_map: dict[uuid.UUID, dict[str, int]] = {}
    if "stats" in all_include_keys and persons:
        stats_map = await handler.get_persons_stats(clan_id, [person.id for person in persons])

    # Per-person include sets (global + per-id overrides), then ONE batched
    # query per include token covering exactly the persons that asked for it.
    include_sets = {
        person.id: set(includes) | set(includes_by_id.get(person.id, [])) for person in persons
    }
    include_ids: dict[str, list[uuid.UUID]] = {}
    for token in ("marriages", "parent_child", "timeline", "documents"):
        ids_needing = [p.id for p in persons if token in include_sets[p.id]]
        if ids_needing:
            include_ids[token] = ids_needing
    included_maps = await handler.get_included_data_batch(clan_id, include_ids)

    data = []
    for person in persons:
        p_dict = _serialize_person_by_profile(person, body.profile)

        if "stats" in all_include_keys and person.id in stats_map:
            p_dict["stats"] = stats_map[person.id]

        for token, per_person in included_maps.items():
            if token in include_sets[person.id]:
                p_dict[token] = per_person.get(person.id, [])

        data.append(filter_dict(p_dict, field_set))

    return {"data": data, "meta": {"errors": errors}}


@router.get("/{person_id}", responses=ok(PersonResponse))
async def get_person(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    role: ClanRole = RequireViewer,
    include: str | None = Query(
        None,
        description=(
            "Comma-separated embedded resources. Supported: "
            "marriages,parent_child,timeline,documents"
        ),
    ),
    fields: str | None = Query(
        None,
        description="Comma-separated sparse fields. Example: id,full_name,gender,marriages",
    ),
    profile: str = Query(
        "full",
        pattern="^(summary|detail|full)$",
        description="Response profile. summary/detail/full",
    ),
) -> dict[str, Any]:
    """Get a single person's full detail."""
    person = await handler.get(GetPerson(person_id=person_id, clan_id=clan_id))
    await handler.redact_pii(
        [person], viewer_role=role.value, viewer_user_id=uuid.UUID(current_user["sub"])
    )
    p_dict = _serialize_person_by_profile(person, profile)

    includes = parse_includes(include)
    if includes:
        included_data = await _fetch_included_data(handler, clan_id, person_id, includes)
        p_dict.update(included_data)

    p_dict = filter_dict(p_dict, parse_field_set(fields, include=include))

    return {"data": p_dict}


@router.patch("/{person_id}", responses=ok(PersonResponse))
async def update_person(
    person_id: uuid.UUID,
    body: PersonUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonCommandHandler = Depends(get_person_command_handler),
    # RequireViewer (not RequireEditor) is intentional: the handler grants a viewer
    # edit access ONLY to their own linked person and ONLY whitelisted fields, while
    # editors/admins get full edits. See PersonCommandHandler.update.
    user_role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Update a person's details."""
    changes = body.model_dump(exclude_unset=True)
    expected_version = changes.pop("expected_version")
    person = await handler.update(
        UpdatePerson(
            person_id=person_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, user_role.value),
            changes=changes,
            expected_version=expected_version,
        )
    )
    return {"data": person.model_dump()}


@router.delete("/{person_id}", responses=ok_message())
async def delete_person(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonCommandHandler = Depends(get_person_command_handler),
    role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Soft-delete a person (admin only)."""
    await handler.delete(
        DeletePerson(
            person_id=person_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, role.value),
        )
    )
    return {"data": {"message": t("person.deleted"), "id": str(person_id)}}


@router.post("/{person_id}/restore", responses=ok(PersonResponse))
async def restore_person(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonCommandHandler = Depends(get_person_command_handler),
    role: ClanRole = RequireAdmin,
) -> dict[str, Any]:
    """Restore a soft-deleted person (admin only)."""
    await handler.restore(
        RestorePerson(
            person_id=person_id,
            clan_id=clan_id,
            actor=ActorInfo.from_jwt(current_user, role.value),
        )
    )
    return {"data": {"message": t("person.restored"), "id": str(person_id)}}


@router.post("/{person_id}/claim", status_code=201)
async def submit_identity_claim(
    person_id: uuid.UUID,
    body: IdentityClaimSubmit,
    current_user: dict[str, Any] = Depends(get_current_user),
    handler: ClaimCommandHandler = Depends(get_claim_command_handler),
    role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Submit a claim for linking a user profile to a person in the family tree."""
    user_id = uuid.UUID(current_user["sub"])
    result = await handler.submit_claim(
        user_id=user_id,
        person_id=person_id,
        requester_note=body.requester_note,
    )
    return {"data": result.model_dump()}


# ── Sub-resources  ────────────────────────────────────────────────


@router.get("/{person_id}/marriages")
async def person_marriages(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    role: ClanRole = RequireViewer,
    fields: str | None = Query(None),
) -> dict[str, Any]:
    """Get all marriages for a person."""
    await handler.get(GetPerson(person_id=person_id, clan_id=clan_id))
    marriages = await handler.get_marriages(clan_id, person_id)
    return {"data": _filter_list_by_fields(marriages, fields)}


@router.get("/{person_id}/parent-child")
async def person_parent_child(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    role: ClanRole = RequireViewer,
    fields: str | None = Query(None),
) -> dict[str, Any]:
    """Get all parent-child relationships for a person."""
    await handler.get(GetPerson(person_id=person_id, clan_id=clan_id))
    links = await handler.get_parent_child(clan_id, person_id)
    return {"data": _filter_list_by_fields(links, fields)}


@router.get("/{person_id}/documents")
async def person_documents(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    role: ClanRole = RequireViewer,
    fields: str | None = Query(None),
) -> dict[str, Any]:
    """Get all documents for a person."""
    await handler.get(GetPerson(person_id=person_id, clan_id=clan_id))
    docs = await handler.get_documents(clan_id, person_id)
    return {"data": _filter_list_by_fields(docs, fields)}


@router.get("/{person_id}/events")
async def person_events(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    role: ClanRole = RequireViewer,
    fields: str | None = Query(None),
) -> dict[str, Any]:
    """Get all events for a person."""
    await handler.get(GetPerson(person_id=person_id, clan_id=clan_id))
    events = await handler.get_events(clan_id, person_id)
    return {"data": _filter_list_by_fields(events, fields)}


@router.get("/{person_id}/timeline")
async def person_timeline(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Return a chronological timeline of life events for a person."""
    await handler.get(GetPerson(person_id=person_id, clan_id=clan_id))
    timeline = await handler.get_timeline(clan_id, person_id)
    return {"data": timeline}
