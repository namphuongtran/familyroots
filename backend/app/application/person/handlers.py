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
from app.domain.person.entity import Person
from app.domain.person.query_port import PersonQueryPort
from app.domain.person.repository import PersonFilters, PersonRepository, PersonSearchResult
from app.domain.shared.exceptions import EntityNotFoundError, ForbiddenError
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.models.user_profile import UserProfile
from app.schemas.person import PersonResponse


class PersonCommandHandler:
    """Handles Person write operations (create, update, delete, restore)."""

    def __init__(self, repo: PersonRepository, uow: SqlAlchemyUnitOfWork) -> None:
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
            birth_date_approx=cmd.birth_date_approx,
            death_date=cmd.death_date,
            death_date_approx=cmd.death_date_approx,
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

        self._uow.track(person)
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

        if cmd.actor.role == "viewer":
            user_profile = await self._uow.session.get(UserProfile, cmd.actor.user_id)
            if not user_profile or user_profile.person_id != cmd.person_id:
                raise ForbiddenError("insufficient_permissions")

            allowed_fields = {
                "phone", "email", "avatar_url", "residence_place",
                "biography", "notes", "religion", "occupation",
                "education_level", "title_rank"
            }
            invalid_fields = set(cmd.changes.keys()) - allowed_fields
            if invalid_fields:
                raise ForbiddenError(f"unauthorized_fields_update: {', '.join(invalid_fields)}")

        person.update(cmd.changes, cmd.actor, cmd.clan_id)
        self._uow.track(person)
        await self._repo.save(person)
        await self._uow.commit()
        return PersonResponse.model_validate(person)

    async def delete(self, cmd: DeletePerson) -> None:
        """Soft-delete a person."""
        person = await self._repo.get_in_clan(cmd.person_id, cmd.clan_id)
        if not person:
            raise EntityNotFoundError("person_not_found")

        person.soft_delete(cmd.actor, cmd.clan_id)
        self._uow.track(person)
        await self._repo.save(person)
        await self._uow.commit()

    async def restore(self, cmd: RestorePerson) -> PersonResponse:
        """Restore a soft-deleted person."""
        person = await self._repo.get_in_clan(cmd.person_id, cmd.clan_id)
        if not person:
            raise EntityNotFoundError("person_not_found")

        person.restore(cmd.actor, cmd.clan_id)
        self._uow.track(person)
        await self._repo.save(person)
        await self._uow.commit()
        return PersonResponse.model_validate(person)


class PersonQueryHandler:
    """Handles Person read operations (list, search, get, timeline)."""

    def __init__(self, repo: PersonRepository, query_port: PersonQueryPort | None = None) -> None:
        self._repo = repo
        self._query_port = query_port

    async def list(self, query: ListPersons) -> tuple[list[PersonResponse], int]:
        """List persons with filtering, pagination, and total count."""
        filters = PersonFilters(
            gender=query.gender,
            is_deleted=query.is_deleted,
            generation=query.generation,
            branch_id=query.branch_id,
        )
        persons = await self._repo.list_in_clan(
            query.clan_id, filters, query.cursor, query.limit
        )
        total = await self._repo.count_in_clan(query.clan_id, query.is_deleted)
        return [PersonResponse.model_validate(p) for p in persons], total

    async def get(self, query: GetPerson) -> PersonResponse:
        """Get a single person."""
        person = await self._repo.get_in_clan(query.person_id, query.clan_id)
        if not person:
            raise EntityNotFoundError("person_not_found")
        return PersonResponse.model_validate(person)

    async def search(self, query: SearchPersons) -> list[PersonSearchResult]:
        """Search persons by name."""
        return await self._repo.search(query.clan_id, query.query, query.limit)

    async def get_persons_stats(self, person_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
        """Fetch statistics for a list of persons."""
        return await self._repo.get_stats_for_persons(person_ids)

    async def get_marriages(self, person_id: uuid.UUID) -> list[dict[str, Any]]:
        if not self._query_port:
            raise NotImplementedError("Query port not configured for this handler")
        return await self._query_port.get_marriages(person_id)

    async def get_parent_child(self, person_id: uuid.UUID) -> list[dict[str, Any]]:
        if not self._query_port:
            raise NotImplementedError("Query port not configured for this handler")
        return await self._query_port.get_parent_child_links(person_id)

    async def get_documents(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        if not self._query_port:
            raise NotImplementedError("Query port not configured for this handler")
        return await self._query_port.get_documents(clan_id, person_id)

    async def get_events(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        if not self._query_port:
            raise NotImplementedError("Query port not configured for this handler")
        return await self._query_port.get_events(clan_id, person_id)

    async def get_timeline(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        from app.application.person.commands import GetPerson
        from app.schemas.event import TimelineEvent
        from app.services.translator import t

        person = await self.get(GetPerson(person_id=person_id, clan_id=clan_id))
        timeline = []

        if person.birth_date:
            timeline.append(TimelineEvent(event_date=person.birth_date, date_approx=person.birth_date_approx, event_type="birth", title=t("timeline.birth")).model_dump())
        if person.death_date:
            timeline.append(TimelineEvent(event_date=person.death_date, date_approx=person.death_date_approx, event_type="death", title=t("timeline.death")).model_dump())

        spouse_result = await self._session.execute(
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
            timeline.append(TimelineEvent(event_date=row["marriage_date"], date_approx=False, event_type="marriage", title=t("timeline.marriage"), related_person_id=row["spouse_id"], related_person_name=row["spouse_name"]).model_dump())

        events_result = await self._session.execute(
            select(Event).where(Event.clan_id == clan_id, Event.person_id == person_id)
        )
        for ev in events_result.scalars().all():
            timeline.append(TimelineEvent(event_date=ev.event_date, date_approx=False, event_type=ev.event_type, title=ev.title, description=ev.description).model_dump())

        timeline.sort(key=lambda e: e.get("event_date") or date.max)
        return timeline
