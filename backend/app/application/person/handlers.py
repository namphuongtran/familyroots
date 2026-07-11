"""Person use-case handlers.

Orchestrates domain entities + repository + UoW to execute commands/queries.
Each handler method is a single use case — one public method per action.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.application.person.commands import (
    CreatePerson,
    DeletePerson,
    GetPerson,
    ListPersons,
    RestorePerson,
    SearchPersons,
    UpdatePerson,
)
from app.core.pagination import encode_fields_cursor
from app.domain.person.entity import Person
from app.domain.person.query_port import PersonQueryPort
from app.domain.person.repository import PersonFilters, PersonRepository, PersonSearchResult
from app.domain.shared.exceptions import EntityNotFoundError, ForbiddenError
from app.domain.shared.unit_of_work import UnitOfWork
from app.schemas.person import PersonResponse

# Contact PII hidden from ordinary clan members (L11). Genealogy content (names, dates,
# places, lineage, bio, …) stays visible to every member.
_PII_FIELDS = ("phone", "email")
_ADMIN_ROLE = "admin"


async def _redact_person_pii(
    repo: PersonRepository,
    persons: list[PersonResponse],
    *,
    viewer_role: str,
    viewer_user_id: uuid.UUID,
) -> None:
    """Null contact PII in-place unless the viewer may see it.

    An admin sees everyone's contact details, and any member sees their OWN linked
    person's; for everyone else phone/email are nulled. Shared by the read path AND the
    update-response path so PII can't leak through either surface.
    """
    if viewer_role == _ADMIN_ROLE:
        return
    own_person_id = await repo.get_linked_person_id(viewer_user_id)
    for person in persons:
        if person.id != own_person_id:
            for field in _PII_FIELDS:
                setattr(person, field, None)


class PersonCommandHandler:
    """Handles Person write operations (create, update, delete, restore)."""

    def __init__(self, repo: PersonRepository, uow: UnitOfWork) -> None:
        self._repo = repo
        self._uow = uow

    async def create(self, cmd: CreatePerson) -> PersonResponse:
        """Create a new person and their clan membership."""
        person = Person.create(
            full_name=cmd.full_name,
            actor=cmd.actor,
            clan_id=cmd.clan_id,
            gender=cmd.gender,
            birth_name=cmd.birth_name,
            courtesy_name=cmd.courtesy_name,
            posthumous_name=cmd.posthumous_name,
            alias_name=cmd.alias_name,
            birth_date=cmd.birth_date,
            birth_date_precision=cmd.birth_date_precision,
            birth_date_display=cmd.birth_date_display,
            death_date=cmd.death_date,
            death_date_precision=cmd.death_date_precision,
            death_date_display=cmd.death_date_display,
            lunar_birth_date=cmd.lunar_birth_date,
            lunar_death_date=cmd.lunar_death_date,
            birth_place=cmd.birth_place,
            death_place=cmd.death_place,
            burial_place=cmd.burial_place,
            tomb_location=cmd.tomb_location,
            residence_place=cmd.residence_place,
            religion=cmd.religion,
            nationality=cmd.nationality,
            occupation=cmd.occupation,
            education_level=cmd.education_level,
            title_rank=cmd.title_rank,
            phone=cmd.phone,
            email=cmd.email,
            biography=cmd.biography,
            avatar_url=cmd.avatar_url,
            notes=cmd.notes,
            created_by_clan_id=cmd.created_by_clan_id or cmd.clan_id,
        )

        await self._repo.save_with_membership(
            person,
            clan_id=cmd.clan_id,
            role=cmd.membership_role,
            generation=cmd.generation,
            is_founder=cmd.is_founder,
            branch_id=cmd.branch_id,
        )
        await self._uow.commit()
        return PersonResponse.model_validate(person)

    async def update(self, cmd: UpdatePerson) -> PersonResponse:
        """Update a person's details."""
        person = await self._repo.get_in_clan(cmd.person_id, cmd.clan_id)
        if not person:
            raise EntityNotFoundError("person_not_found")

        # Self-edit carve-out: a viewer may edit ONLY their own linked person and ONLY
        # the whitelisted fields below. Editors/admins (role != "viewer") skip this and
        # may edit any field. This is why the route uses RequireViewer, not RequireEditor.
        if cmd.actor.role == "viewer":
            linked_person_id = await self._repo.get_linked_person_id(cmd.actor.user_id)
            if linked_person_id != cmd.person_id:
                raise ForbiddenError("insufficient_permissions")

            allowed_fields = {
                "phone",
                "email",
                "avatar_url",
                "residence_place",
                "biography",
                "notes",
                "religion",
                "occupation",
                "education_level",
                "title_rank",
            }
            invalid_fields = set(cmd.changes.keys()) - allowed_fields
            if invalid_fields:
                raise ForbiddenError("field_not_updatable", {"fields": sorted(invalid_fields)})

        person.update(cmd.changes, cmd.actor, cmd.clan_id)
        await self._repo.save(person)
        await self._uow.commit()
        response = PersonResponse.model_validate(person)
        # The PATCH response echoes the person's stored fields — redact contact PII so
        # an editor editing a stranger's record can't read phone/email through it (L11).
        await _redact_person_pii(
            self._repo, [response], viewer_role=cmd.actor.role, viewer_user_id=cmd.actor.user_id
        )
        return response

    async def delete(self, cmd: DeletePerson) -> None:
        """Soft-delete a person."""
        person = await self._repo.get_in_clan(cmd.person_id, cmd.clan_id)
        if not person:
            raise EntityNotFoundError("person_not_found")

        person.soft_delete(cmd.actor, cmd.clan_id)
        await self._repo.save(person)
        await self._uow.commit()

    async def restore(self, cmd: RestorePerson) -> PersonResponse:
        """Restore a soft-deleted person."""
        person = await self._repo.get_in_clan(cmd.person_id, cmd.clan_id, include_deleted=True)
        if not person:
            raise EntityNotFoundError("person_not_found")

        person.restore(cmd.actor, cmd.clan_id)
        await self._repo.save(person)
        await self._uow.commit()
        return PersonResponse.model_validate(person)


class PersonQueryHandler:
    """Handles Person read operations (list, search, get, timeline)."""

    def __init__(self, repo: PersonRepository, query_port: PersonQueryPort | None = None) -> None:
        self._repo = repo
        self._query_port = query_port

    async def list_persons(self, query: ListPersons) -> tuple[list[PersonResponse], dict[str, Any]]:
        """List persons with filtering and cursor pagination.

        Returns ``(data, meta)`` where ``meta`` carries ``cursor``/``has_more``/``limit``
        — no bare total/count_in_clan call here (see repo-level count_in_clan for other
        callers). The list is ordered by ``(full_name, id)``, so the cursor encodes both
        fields (see ``list_in_clan``) — an id-only cursor would skip/duplicate rows
        whenever id-order and full_name-order disagree.
        """
        filters = PersonFilters(
            gender=query.gender,
            generation=query.generation,
            is_deleted=query.is_deleted,
            branch_id=query.branch_id,
        )
        rows = await self._repo.list_in_clan(query.clan_id, filters, query.cursor, query.limit)
        has_more = len(rows) > query.limit
        page = rows[: query.limit]
        cursor = None
        if has_more and page:
            last = page[-1]
            cursor = encode_fields_cursor({"full_name": last.full_name, "id": str(last.id)})
        meta = {
            "cursor": cursor,
            "has_more": has_more,
            "limit": query.limit,
        }
        return [PersonResponse.model_validate(p) for p in page], meta

    async def get(self, query: GetPerson) -> PersonResponse:
        """Get a single person."""
        person = await self._repo.get_in_clan(query.person_id, query.clan_id)
        if not person:
            raise EntityNotFoundError("person_not_found")
        return PersonResponse.model_validate(person)

    async def redact_pii(
        self,
        persons: list[PersonResponse],
        *,
        viewer_role: str,
        viewer_user_id: uuid.UUID,
    ) -> None:
        """Redact contact PII on the read path (see ``_redact_person_pii``), so it can't
        be bypassed via ?profile=full."""
        await _redact_person_pii(
            self._repo, persons, viewer_role=viewer_role, viewer_user_id=viewer_user_id
        )

    async def search(self, query: SearchPersons) -> list[PersonSearchResult]:
        """Search persons by name."""
        return await self._repo.search(query.clan_id, query.query, query.limit)

    async def get_persons_stats(
        self, clan_id: uuid.UUID, person_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, int]]:
        """Fetch statistics for a list of persons, scoped to the caller's clan."""
        return await self._repo.get_stats_for_persons(clan_id, person_ids)

    async def get_marriages(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        if not self._query_port:
            raise NotImplementedError("Query port not configured for this handler")
        return await self._query_port.get_marriages(clan_id, person_id)

    async def get_parent_child(
        self, clan_id: uuid.UUID, person_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        if not self._query_port:
            raise NotImplementedError("Query port not configured for this handler")
        return await self._query_port.get_parent_child_links(clan_id, person_id)

    async def get_documents(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        if not self._query_port:
            raise NotImplementedError("Query port not configured for this handler")
        return await self._query_port.get_documents(clan_id, person_id)

    async def get_events(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        if not self._query_port:
            raise NotImplementedError("Query port not configured for this handler")
        return await self._query_port.get_events(clan_id, person_id)

    async def get_timeline(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return a chronological timeline for a person.

        Delegates entirely to the query port which handles fetching
        birth/death dates, marriages, and events from the database.
        """
        if not self._query_port:
            raise NotImplementedError("Query port not configured for this handler")
        return await self._query_port.get_timeline(clan_id, person_id)
