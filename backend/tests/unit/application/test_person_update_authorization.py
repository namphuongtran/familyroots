"""Pin update_person authorization: viewers edit only their own person, whitelisted fields."""

import uuid
from datetime import UTC, datetime

import pytest

from app.application.person.commands import UpdatePerson
from app.application.person.handlers import PersonCommandHandler
from app.domain.shared.exceptions import ForbiddenError
from app.domain.shared.value_objects import ActorInfo

_NOW = datetime.now(UTC)


class _PersonEntity:
    """Minimal fake person that satisfies PersonResponse.model_validate(from_attributes=True)."""

    def __init__(self):
        self.id = uuid.uuid4()
        self.changes_applied = None
        # Fields required by PersonResponse
        self.full_name = "Test Person"
        self.gender = "unknown"
        self.birth_date_approx = False
        self.death_date_approx = False
        self.nationality = "VN"
        self.is_deleted = False
        self.created_by = uuid.uuid4()
        self.updated_by = None
        self.created_at = _NOW
        self.updated_at = _NOW
        # Optional fields
        self.created_by_clan_id = None
        self.birth_name = None
        self.courtesy_name = None
        self.posthumous_name = None
        self.alias_name = None
        self.birth_date = None
        self.death_date = None
        self.lunar_birth_date = None
        self.lunar_death_date = None
        self.birth_place = None
        self.death_place = None
        self.burial_place = None
        self.tomb_location = None
        self.residence_place = None
        self.religion = None
        self.occupation = None
        self.education_level = None
        self.title_rank = None
        self.phone = None
        self.email = None
        self.biography = None
        self.avatar_url = None
        self.notes = None

    def update(self, changes, actor, clan_id):
        self.changes_applied = changes


class _Profile:
    def __init__(self, person_id):
        self.person_id = person_id


class _FakeSession:
    def __init__(self, profile):
        self._profile = profile

    async def get(self, model, key):
        return self._profile


class _FakeUow:
    def __init__(self, profile):
        self.session = _FakeSession(profile)
        self.commits = 0

    def track(self, agg):
        pass

    async def commit(self):
        self.commits += 1


class _FakeRepo:
    def __init__(self, person):
        self._person = person

    async def get_in_clan(self, person_id, clan_id):
        return self._person

    async def save(self, person):
        pass


def _actor(role, user_id):
    # ActorInfo is a plain dataclass with user_id: uuid.UUID and role: str.
    return ActorInfo(user_id=user_id, role=role)


@pytest.mark.asyncio
async def test_viewer_can_edit_own_whitelisted_field():
    person = _PersonEntity()
    uid = uuid.uuid4()
    handler = PersonCommandHandler(_FakeRepo(person), _FakeUow(_Profile(person.id)))  # type: ignore[arg-type]
    cmd = UpdatePerson(
        person_id=person.id,
        clan_id=uuid.uuid4(),
        actor=_actor("viewer", uid),
        changes={"phone": "0900000000"},
    )
    await handler.update(cmd)
    assert person.changes_applied == {"phone": "0900000000"}


@pytest.mark.asyncio
async def test_viewer_cannot_edit_other_person():
    person = _PersonEntity()
    uid = uuid.uuid4()
    # profile is linked to a DIFFERENT person
    handler = PersonCommandHandler(_FakeRepo(person), _FakeUow(_Profile(uuid.uuid4())))  # type: ignore[arg-type]
    cmd = UpdatePerson(
        person_id=person.id,
        clan_id=uuid.uuid4(),
        actor=_actor("viewer", uid),
        changes={"phone": "x"},
    )
    with pytest.raises(ForbiddenError):
        await handler.update(cmd)


@pytest.mark.asyncio
async def test_viewer_cannot_edit_nonwhitelisted_field():
    person = _PersonEntity()
    uid = uuid.uuid4()
    handler = PersonCommandHandler(_FakeRepo(person), _FakeUow(_Profile(person.id)))  # type: ignore[arg-type]
    cmd = UpdatePerson(
        person_id=person.id,
        clan_id=uuid.uuid4(),
        actor=_actor("viewer", uid),
        changes={"full_name": "Hacked"},
    )
    with pytest.raises(ForbiddenError):
        await handler.update(cmd)


@pytest.mark.asyncio
async def test_editor_can_edit_any_field():
    person = _PersonEntity()
    handler = PersonCommandHandler(_FakeRepo(person), _FakeUow(_Profile(uuid.uuid4())))  # type: ignore[arg-type]
    cmd = UpdatePerson(
        person_id=person.id,
        clan_id=uuid.uuid4(),
        actor=_actor("editor", uuid.uuid4()),
        changes={"full_name": "New Name"},
    )
    await handler.update(cmd)
    assert person.changes_applied == {"full_name": "New Name"}
