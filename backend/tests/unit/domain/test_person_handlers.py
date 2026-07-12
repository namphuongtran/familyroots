"""Unit tests for Person use-case handlers (commands & queries)."""

import uuid
from unittest.mock import AsyncMock

import pytest

from app.application.person.commands import (
    CreatePerson,
    DeletePerson,
    GetPerson,
    ListPersons,
    UpdatePerson,
)
from app.application.person.handlers import PersonCommandHandler, PersonQueryHandler
from app.core.pagination import encode_fields_cursor
from app.domain.person.entity import Person
from app.domain.shared.exceptions import EntityNotFoundError
from app.domain.shared.value_objects import ActorInfo

# ── Fixtures ────────────────────────────────────────────────────


def _make_actor() -> ActorInfo:
    return ActorInfo(user_id=uuid.uuid4(), role="editor")


def _make_person(name: str = "Test Person") -> Person:
    return Person.create(full_name=name, actor=_make_actor(), clan_id=uuid.uuid4())


# ── PersonCommandHandler ────────────────────────────────────────


class TestPersonCommandHandlerCreate:
    @pytest.mark.asyncio
    async def test_create_calls_repo_and_commits(self) -> None:
        """Create wires through repo.save_with_membership → uow.commit."""
        mock_repo = AsyncMock()
        mock_uow = AsyncMock()
        mock_uow.track = lambda agg: None  # sync method

        handler = PersonCommandHandler(mock_repo, mock_uow)

        cmd = CreatePerson(
            actor=_make_actor(),
            clan_id=uuid.uuid4(),
            full_name="Nguyễn Văn A",
        )
        result = await handler.create(cmd)

        assert result.full_name == "Nguyễn Văn A"
        mock_repo.save_with_membership.assert_awaited_once()
        mock_uow.commit.assert_awaited_once()


class TestPersonCommandHandlerUpdate:
    @pytest.mark.asyncio
    async def test_update_modifies_and_commits(self) -> None:
        """Update loads, mutates, saves, commits."""
        person = _make_person("Before")
        person.collect_events()  # drain

        mock_repo = AsyncMock()
        mock_repo.get_in_clan.return_value = person
        mock_uow = AsyncMock()
        mock_uow.track = lambda agg: None

        handler = PersonCommandHandler(mock_repo, mock_uow)
        cmd = UpdatePerson(
            person_id=person.id,
            clan_id=uuid.uuid4(),
            actor=_make_actor(),
            expected_version=1,
            changes={"full_name": "After"},
        )
        result = await handler.update(cmd)

        assert result.full_name == "After"
        mock_repo.save.assert_awaited_once()
        mock_uow.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_response_redacts_pii_for_editor_editing_stranger(self) -> None:
        """L11: the PATCH response must not leak a stranger's phone/email to an editor."""
        person = _make_person("Before")
        person.phone = "0900000000"
        person.email = "a@example.com"
        person.collect_events()

        mock_repo = AsyncMock()
        mock_repo.get_in_clan.return_value = person
        mock_repo.get_linked_person_id.return_value = uuid.uuid4()  # editor linked elsewhere
        mock_uow = AsyncMock()
        mock_uow.track = lambda agg: None

        handler = PersonCommandHandler(mock_repo, mock_uow)
        result = await handler.update(
            UpdatePerson(
                person_id=person.id,
                clan_id=uuid.uuid4(),
                actor=ActorInfo(user_id=uuid.uuid4(), role="editor"),
                expected_version=1,
                changes={"full_name": "After"},
            )
        )
        assert result.full_name == "After"
        assert result.phone is None and result.email is None

    @pytest.mark.asyncio
    async def test_update_response_keeps_pii_for_admin(self) -> None:
        person = _make_person("Before")
        person.phone = "0900000000"
        person.collect_events()

        mock_repo = AsyncMock()
        mock_repo.get_in_clan.return_value = person
        mock_uow = AsyncMock()
        mock_uow.track = lambda agg: None

        handler = PersonCommandHandler(mock_repo, mock_uow)
        result = await handler.update(
            UpdatePerson(
                person_id=person.id,
                clan_id=uuid.uuid4(),
                actor=ActorInfo(user_id=uuid.uuid4(), role="admin"),
                expected_version=1,
                changes={"full_name": "After"},
            )
        )
        assert result.phone == "0900000000"

    @pytest.mark.asyncio
    async def test_update_raises_not_found(self) -> None:
        """Update raises EntityNotFoundError when person not in clan."""
        mock_repo = AsyncMock()
        mock_repo.get_in_clan.return_value = None
        mock_uow = AsyncMock()

        handler = PersonCommandHandler(mock_repo, mock_uow)
        cmd = UpdatePerson(
            person_id=uuid.uuid4(),
            clan_id=uuid.uuid4(),
            actor=_make_actor(),
            expected_version=1,
            changes={"full_name": "X"},
        )
        with pytest.raises(EntityNotFoundError):
            await handler.update(cmd)


class TestPersonCommandHandlerDelete:
    @pytest.mark.asyncio
    async def test_delete_soft_deletes_and_commits(self) -> None:
        person = _make_person()
        person.collect_events()

        mock_repo = AsyncMock()
        mock_repo.get_in_clan.return_value = person
        mock_uow = AsyncMock()
        mock_uow.track = lambda agg: None

        handler = PersonCommandHandler(mock_repo, mock_uow)
        await handler.delete(
            DeletePerson(person_id=person.id, clan_id=uuid.uuid4(), actor=_make_actor())
        )

        assert person.is_deleted is True
        mock_repo.save.assert_awaited_once()
        mock_uow.commit.assert_awaited_once()


# ── PersonQueryHandler ──────────────────────────────────────────


class TestPersonQueryHandlerGet:
    @pytest.mark.asyncio
    async def test_get_returns_person(self) -> None:
        person = _make_person()
        mock_repo = AsyncMock()
        mock_repo.get_in_clan.return_value = person

        handler = PersonQueryHandler(mock_repo)
        result = await handler.get(GetPerson(person_id=person.id, clan_id=uuid.uuid4()))
        assert result.id == person.id

    @pytest.mark.asyncio
    async def test_get_raises_not_found(self) -> None:
        mock_repo = AsyncMock()
        mock_repo.get_in_clan.return_value = None

        handler = PersonQueryHandler(mock_repo)
        with pytest.raises(EntityNotFoundError):
            await handler.get(GetPerson(person_id=uuid.uuid4(), clan_id=uuid.uuid4()))


class TestPersonQueryHandlerList:
    """F-1 5a: list_persons returns (data, meta) — no more bare total/count_in_clan."""

    @pytest.mark.asyncio
    async def test_list_persons_reports_has_more_and_cursor_from_extra_row(self) -> None:
        """Repo returns limit+1 rows; handler must truncate to limit and set cursor
        to the last row of the *truncated* page (not the extra lookahead row)."""
        limit = 2
        rows = [_make_person(f"P{i}") for i in range(limit + 1)]
        mock_repo = AsyncMock()
        mock_repo.list_in_clan.return_value = rows

        handler = PersonQueryHandler(mock_repo)
        data, meta = await handler.list_persons(ListPersons(clan_id=uuid.uuid4(), limit=limit))

        assert len(data) == limit
        assert [p.id for p in data] == [rows[0].id, rows[1].id]
        last = rows[limit - 1]
        expected_cursor = encode_fields_cursor({"full_name": last.full_name, "id": str(last.id)})
        assert meta == {"cursor": expected_cursor, "has_more": True, "limit": limit}
        mock_repo.count_in_clan.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_persons_no_more_pages_has_no_cursor(self) -> None:
        """Repo returns <= limit rows: has_more False, no cursor, nothing truncated."""
        limit = 5
        rows = [_make_person(f"P{i}") for i in range(2)]
        mock_repo = AsyncMock()
        mock_repo.list_in_clan.return_value = rows

        handler = PersonQueryHandler(mock_repo)
        data, meta = await handler.list_persons(ListPersons(clan_id=uuid.uuid4(), limit=limit))

        assert len(data) == 2
        assert meta == {"cursor": None, "has_more": False, "limit": limit}
        mock_repo.count_in_clan.assert_not_awaited()
