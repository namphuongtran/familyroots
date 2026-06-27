"""Persons API routes — thin controller delegating to use-case handlers.

CRUD and search operations use the DDD Person bounded context.
Sub-resource endpoints (marriages, parent-child, documents, events, timeline)
remain DB-direct until their respective bounded contexts are migrated.
"""

import asyncio
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
from app.domain.shared.exceptions import EntityNotFoundError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.dependencies import (
    get_claim_command_handler,
    get_person_command_handler,
    get_person_query_handler,
)
from app.schemas.claim import IdentityClaimResponse, IdentityClaimSubmit
from app.schemas.person import (
    PersonBatchGetRequest,
    PersonCreateRequest,
    PersonDetail,
    PersonSummary,
    PersonUpdateRequest,
)
from app.services.translator import t

router = APIRouter()


def _serialize_person_by_profile(person: Any, profile: str) -> dict[str, Any]:
    """Serialize a person to the selected response profile."""
    if profile == "summary":
        return PersonSummary.model_validate(person).model_dump(exclude_unset=True)
    if profile == "detail":
        return PersonDetail.model_validate(person).model_dump(exclude_unset=True)
    return person.model_dump()


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
    persons, total = await handler.list_persons(
        ListPersons(
            clan_id=clan_id,
            gender=gender,
            generation=generation,
            cursor=cursor,
            limit=limit,
        )
    )

    includes = parse_includes(include)
    include_set = set(includes)
    field_set = parse_field_set(fields, include=include)

    stats_map = {}
    if "stats" in include_set and persons:
        person_ids = [p.id for p in persons]
        stats_map = await handler.get_persons_stats(person_ids)

    res_data = []
    for p in persons:
        p_dict = _serialize_person_by_profile(p, profile)

        if "stats" in include_set and p.id in stats_map:
            p_dict["stats"] = stats_map[p.id]

        res_data.append(filter_dict(p_dict, field_set))

    return {
        "data": res_data,
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
                "membership_role": r.membership_role,
                "is_founder": r.is_founder,
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


async def _fetch_included_data(
    handler: PersonQueryHandler,
    clan_id: uuid.UUID,
    person_id: uuid.UUID,
    includes: list[str],
) -> dict[str, list[Any]]:
    tasks = {}
    if "marriages" in includes:
        tasks["marriages"] = handler.get_marriages(clan_id, person_id)
    if "parent_child" in includes:
        tasks["parent_child"] = handler.get_parent_child(clan_id, person_id)
    if "timeline" in includes:
        tasks["timeline"] = handler.get_timeline(clan_id, person_id)
    if "documents" in includes:
        tasks["documents"] = handler.get_documents(clan_id, person_id)

    if not tasks:
        return {}

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    res_dict = {}
    for key, res in zip(tasks.keys(), results, strict=False):
        res_dict[key] = res if isinstance(res, list) else []
    return res_dict


def _filter_list_by_fields(items: list[Any], fields: str | None) -> list[Any]:
    return filter_list(items, parse_field_set(fields))


@router.post("/batch")
async def batch_get_persons(
    body: PersonBatchGetRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    _role: ClanRole = RequireViewer,
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

    person_tasks = [
        handler.get(GetPerson(person_id=person_id, clan_id=clan_id)) for person_id in person_ids
    ]
    person_results = await asyncio.gather(*person_tasks, return_exceptions=True)

    persons = []
    errors: list[dict[str, str]] = []
    for person_id, result in zip(person_ids, person_results, strict=False):
        if isinstance(result, EntityNotFoundError):
            errors.append({"id": str(person_id), "code": "person_not_found"})
            continue
        if isinstance(result, Exception):
            raise result
        persons.append(result)

    includes = parse_includes(body.include)
    includes_by_id = _parse_include_by_id(body.include_by_id)
    all_include_keys = set(includes)
    for per_person_includes in includes_by_id.values():
        all_include_keys.update(per_person_includes)
    include_union = ",".join(sorted(all_include_keys)) if all_include_keys else None
    field_set = parse_field_set(body.fields, include=include_union)

    stats_map: dict[uuid.UUID, dict[str, int]] = {}
    if "stats" in all_include_keys and persons:
        stats_map = await handler.get_persons_stats([person.id for person in persons])

    included_results: list[dict[str, list[Any]]] = await asyncio.gather(
        *[
            _fetch_included_data(
                handler,
                clan_id,
                person.id,
                list(dict.fromkeys([*includes, *includes_by_id.get(person.id, [])])),
            )
            for person in persons
        ]
    )

    data = []
    for idx, person in enumerate(persons):
        p_dict = _serialize_person_by_profile(person, body.profile)

        if "stats" in all_include_keys and person.id in stats_map:
            p_dict["stats"] = stats_map[person.id]

        if idx < len(included_results):
            p_dict.update(included_results[idx])

        data.append(filter_dict(p_dict, field_set))

    return {"data": data, "errors": errors}


@router.get("/{person_id}")
async def get_person(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    _role: ClanRole = RequireViewer,
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
    p_dict = _serialize_person_by_profile(person, profile)

    includes = parse_includes(include)
    if includes:
        included_data = await _fetch_included_data(handler, clan_id, person_id, includes)
        p_dict.update(included_data)

    p_dict = filter_dict(p_dict, parse_field_set(fields, include=include))

    return {"data": p_dict}


@router.patch("/{person_id}")
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
    handler: ClaimCommandHandler = Depends(get_claim_command_handler),
    _role: ClanRole = RequireViewer,
) -> IdentityClaimResponse:
    """Submit a claim for linking a user profile to a person in the family tree."""
    user_id = uuid.UUID(current_user["sub"])
    return await handler.submit_claim(
        user_id=user_id,
        person_id=person_id,
        requester_note=body.requester_note,
    )


# ── Sub-resources  ────────────────────────────────────────────────


@router.get("/{person_id}/marriages")
async def person_marriages(
    person_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: PersonQueryHandler = Depends(get_person_query_handler),
    _role: ClanRole = RequireViewer,
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
    _role: ClanRole = RequireViewer,
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
    _role: ClanRole = RequireViewer,
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
    _role: ClanRole = RequireViewer,
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
    _role: ClanRole = RequireViewer,
) -> dict[str, Any]:
    """Return a chronological timeline of life events for a person."""
    await handler.get(GetPerson(person_id=person_id, clan_id=clan_id))
    timeline = await handler.get_timeline(clan_id, person_id)
    return {"data": timeline}
