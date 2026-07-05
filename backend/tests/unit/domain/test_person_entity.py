"""Unit tests for Person domain entity and events."""

import uuid
from datetime import date

import pytest

from app.domain.person.entity import Person
from app.domain.person.events import (
    PersonCreated,
    PersonDeleted,
    PersonRestored,
    PersonUpdated,
)
from app.domain.shared.exceptions import BusinessRuleViolation
from app.domain.shared.value_objects import ActorInfo

# ── Person.create ────────────────────────────────────────────────


class TestPersonCreate:
    def test_create_sets_fields(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        clan_id = uuid.uuid4()
        person = Person.create(
            full_name="Nguyễn Văn A",
            actor=actor,
            clan_id=clan_id,
            gender="male",
            birth_date=date(1990, 1, 15),
        )
        assert person.full_name == "Nguyễn Văn A"
        assert person.gender == "male"
        assert person.birth_date == date(1990, 1, 15)
        assert person.created_by == actor.user_id
        assert not person.is_deleted

    def test_create_emits_person_created_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        clan_id = uuid.uuid4()
        person = Person.create(full_name="Test", actor=actor, clan_id=clan_id)

        events = person.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], PersonCreated)
        assert events[0].person_id == person.id
        assert events[0].clan_id == clan_id
        assert events[0].actor_id == actor.user_id
        assert events[0].action == "person.create"
        assert events[0].resource_type == "person"


# ── Person.update ────────────────────────────────────────────────


class TestPersonUpdate:
    def test_update_changes_fields(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        clan_id = uuid.uuid4()
        person = Person.create(full_name="Before", actor=actor, clan_id=clan_id)
        person.collect_events()  # drain creation event

        person.update({"full_name": "After", "gender": "female"}, actor, clan_id)
        assert person.full_name == "After"
        assert person.gender == "female"
        assert person.updated_by == actor.user_id

    def test_update_emits_person_updated_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        clan_id = uuid.uuid4()
        person = Person.create(full_name="Test", actor=actor, clan_id=clan_id)
        person.collect_events()

        person.update({"full_name": "Updated"}, actor, clan_id)
        events = person.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], PersonUpdated)
        assert events[0].action == "person.update"
        assert events[0].changes == {"full_name": "Updated"}
        assert events[0].old_values == {"full_name": "Test"}


# ── Person.soft_delete ───────────────────────────────────────────


class TestPersonSoftDelete:
    def test_soft_delete_marks_deleted(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="admin")
        clan_id = uuid.uuid4()
        person = Person.create(full_name="Test", actor=actor, clan_id=clan_id)
        person.collect_events()

        person.soft_delete(actor, clan_id)
        assert person.is_deleted is True
        assert person.deleted_at is not None
        assert person.deleted_by == actor.user_id

    def test_soft_delete_emits_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="admin")
        clan_id = uuid.uuid4()
        person = Person.create(full_name="Test", actor=actor, clan_id=clan_id)
        person.collect_events()

        person.soft_delete(actor, clan_id)
        events = person.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], PersonDeleted)
        assert events[0].action == "person.delete"


# ── Person.restore ───────────────────────────────────────────────


class TestPersonRestore:
    def test_restore_clears_deletion(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="admin")
        clan_id = uuid.uuid4()
        person = Person.create(full_name="Test", actor=actor, clan_id=clan_id)
        person.soft_delete(actor, clan_id)
        person.collect_events()

        person.restore(actor, clan_id)
        assert person.is_deleted is False
        assert person.deleted_at is None
        assert person.deleted_by is None

    def test_restore_emits_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="admin")
        clan_id = uuid.uuid4()
        person = Person.create(full_name="Test", actor=actor, clan_id=clan_id)
        person.soft_delete(actor, clan_id)
        person.collect_events()

        person.restore(actor, clan_id)
        events = person.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], PersonRestored)
        assert events[0].action == "person.restore"


# ── PersonEvents — auto-populate ─────────────────────────────────


class TestPersonEvents:
    def test_created_auto_populates_resource(self) -> None:
        pid = uuid.uuid4()
        e = PersonCreated(person_id=pid, clan_id=uuid.uuid4(), actor_id=uuid.uuid4())
        assert e.action == "person.create"
        assert e.resource_type == "person"
        assert e.resource_id == pid

    def test_deleted_auto_populates_resource(self) -> None:
        pid = uuid.uuid4()
        e = PersonDeleted(person_id=pid, clan_id=uuid.uuid4(), actor_id=uuid.uuid4())
        assert e.action == "person.delete"
        assert e.resource_id == pid

    def test_restored_auto_populates_resource(self) -> None:
        pid = uuid.uuid4()
        e = PersonRestored(person_id=pid, clan_id=uuid.uuid4(), actor_id=uuid.uuid4())
        assert e.action == "person.restore"
        assert e.resource_id == pid


# ── death_date >= birth_date invariant (L5) ──────────────────────


class TestPersonDateInvariant:
    def _actor(self) -> ActorInfo:
        return ActorInfo(user_id=uuid.uuid4(), role="editor")

    def test_create_rejects_death_before_birth(self) -> None:
        with pytest.raises(BusinessRuleViolation, match="death_before_birth"):
            Person.create(
                full_name="X",
                actor=self._actor(),
                clan_id=uuid.uuid4(),
                birth_date=date(1990, 1, 1),
                death_date=date(1980, 1, 1),
            )

    def test_create_allows_valid_equal_or_partial_dates(self) -> None:
        actor, clan = self._actor(), uuid.uuid4()
        # death after birth
        Person.create(
            full_name="A",
            actor=actor,
            clan_id=clan,
            birth_date=date(1990, 1, 1),
            death_date=date(2050, 1, 1),
        )
        # same day (boundary) is allowed
        Person.create(
            full_name="B",
            actor=actor,
            clan_id=clan,
            birth_date=date(1990, 1, 1),
            death_date=date(1990, 1, 1),
        )
        # only one date set → nothing to compare
        Person.create(full_name="C", actor=actor, clan_id=clan, birth_date=date(1990, 1, 1))

    def test_update_rejects_death_before_birth(self) -> None:
        actor, clan = self._actor(), uuid.uuid4()
        person = Person.create(
            full_name="X", actor=actor, clan_id=clan, birth_date=date(1990, 1, 1)
        )
        with pytest.raises(BusinessRuleViolation, match="death_before_birth"):
            person.update({"death_date": date(1980, 1, 1)}, actor, clan)

    def test_reconstruction_does_not_validate(self) -> None:
        # Reads must not raise on legacy bad rows: direct construction (what the
        # persistence mapper does) bypasses the write-path _validate_dates check.
        p = Person(full_name="Legacy", birth_date=date(1990, 1, 1), death_date=date(1980, 1, 1))
        assert p.death_date is not None and p.birth_date is not None
        assert p.death_date < p.birth_date  # constructed without raising
