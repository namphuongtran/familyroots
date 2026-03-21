"""Unit tests for Person use-case handlers (commands & queries)."""

import uuid
from unittest.mock import AsyncMock

import pytest

from app.application.person.commands import CreatePerson, DeletePerson, GetPerson, UpdatePerson
from app.application.person.handlers import PersonCommandHandler, PersonQueryHandler
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
            changes={"full_name": "After"},
        )
        result = await handler.update(cmd)

        assert result.full_name == "After"
        mock_repo.save.assert_awaited_once()
        mock_uow.commit.assert_awaited_once()

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
        result = await handler.get(
            GetPerson(person_id=person.id, clan_id=uuid.uuid4())
        )
        assert result.id == person.id

    @pytest.mark.asyncio
    async def test_get_raises_not_found(self) -> None:
        mock_repo = AsyncMock()
        mock_repo.get_in_clan.return_value = None

        handler = PersonQueryHandler(mock_repo)
        with pytest.raises(EntityNotFoundError):
            await handler.get(GetPerson(person_id=uuid.uuid4(), clan_id=uuid.uuid4()))
