"""Unit tests for Person domain entity and events."""

import uuid
from datetime import date

import pytest

from app.domain.person.entity import _UPDATABLE_FIELDS, Person
from app.domain.person.events import (
    PersonAnonymised,
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


# ── Person.anonymise (ADR-079) ────────────────────────────────────


class TestPersonAnonymise:
    """Read the person after anonymise, not the field list it uses. Every client-writable
    field is filled with a value first, so a field added to the person later that
    anonymise forgets shows up here as a value that survived."""

    # The only written values that may survive: what ADR-027's đời authority reads, and
    # a column default nobody wrote about this person (ADR-079 § "What is kept").
    _KEPT = frozenset({"gender", "nationality"})

    @staticmethod
    def _filled() -> Person:
        person = Person(full_name="Nguyễn Văn Thật")
        for name in _UPDATABLE_FIELDS:
            current = getattr(person, name)
            if name in {"birth_date", "death_date"}:
                value: object = date(1900, 1, 2) if name == "birth_date" else date(1970, 3, 4)
            elif name.endswith("_precision"):
                value = "year"
            else:
                value = f"real-{name}"
            assert value != current
            setattr(person, name, value)
        person.gender = "male"
        person.avatar_url = "https://cdn.example.com/real.jpg"
        return person

    def test_no_written_value_survives_except_the_kept_ones(self) -> None:
        person = self._filled()
        before = dict(vars(person))
        actor = ActorInfo(user_id=uuid.uuid4(), role="admin")

        person.anonymise(actor, uuid.uuid4())

        written = _UPDATABLE_FIELDS | {"avatar_url"}
        survived = {name for name in written if getattr(person, name) == before[name]}
        assert survived == self._KEPT
        assert person.full_name == "Đã ẩn danh"
        assert (person.birth_date_precision, person.death_date_precision) == (
            "unknown",
            "unknown",
        )
        assert person.id == before["id"]
        assert person.is_deleted is False

    def test_the_event_names_the_fields_and_carries_no_erased_value(self) -> None:
        person = self._filled()
        actor = ActorInfo(user_id=uuid.uuid4(), role="admin")
        clan_id = uuid.uuid4()

        person.anonymise(actor, clan_id)

        [event] = person.collect_events()
        assert isinstance(event, PersonAnonymised)
        assert event.action == "person.anonymise"
        assert event.resource_id == person.id
        assert event.clan_id == clan_id
        assert event.old_value is None
        assert event.new_value is not None
        serialized = repr(event.new_value)
        assert "real-" not in serialized and "Thật" not in serialized
        assert "biography" in event.new_value["cleared_fields"]
