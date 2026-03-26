"""Unit tests for Event domain entity and events."""

import uuid
from datetime import date

import pytest

from app.domain.event.entity import Event
from app.domain.event.events import EventCreated, EventDeleted, EventUpdated
from app.domain.shared.exceptions import BusinessRuleViolation
from app.domain.shared.value_objects import ActorInfo

# ── Event.create ─────────────────────────────────────────────────


class TestEventCreate:
    def test_create_sets_fields(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        clan_id = uuid.uuid4()
        event = Event.create(
            clan_id=clan_id,
            actor=actor,
            event_type="death_anniversary",
            title="Giỗ Ông Nội",
            event_date=date(2025, 3, 15),
        )
        assert event.title == "Giỗ Ông Nội"
        assert event.event_type == "death_anniversary"
        assert event.event_date == date(2025, 3, 15)
        assert event.clan_id == clan_id
        assert event.created_by == actor.user_id
        assert event.is_recurring is True  # default

    def test_create_emits_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        event = Event.create(
            clan_id=uuid.uuid4(),
            actor=actor,
            event_type="birthday",
            title="Birthday",
            event_date=date(2000, 6, 1),
        )
        events = event.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], EventCreated)
        assert events[0].event_id == event.id
        assert events[0].action == "event.create"
        assert events[0].resource_type == "event"

    def test_create_rejects_invalid_event_type(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        with pytest.raises(BusinessRuleViolation, match="invalid_event_type"):
            Event.create(
                clan_id=uuid.uuid4(),
                actor=actor,
                event_type="invalid_type",
                title="Test",
                event_date=date(2025, 1, 1),
            )

    def test_create_with_optional_fields(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        person_id = uuid.uuid4()
        event = Event.create(
            clan_id=uuid.uuid4(),
            actor=actor,
            event_type="wedding_anniversary",
            title="Wedding",
            event_date=date(1995, 12, 25),
            person_id=person_id,
            description="50th anniversary celebration",
            is_lunar_calendar=True,
            is_recurring=False,
            notify_days_before=14,
        )
        assert event.person_id == person_id
        assert event.description == "50th anniversary celebration"
        assert event.is_lunar_calendar is True
        assert event.is_recurring is False
        assert event.notify_days_before == 14


# ── Event.update ─────────────────────────────────────────────────


class TestEventUpdate:
    def test_update_changes_fields(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        event = Event.create(
            clan_id=uuid.uuid4(),
            actor=actor,
            event_type="birthday",
            title="Before",
            event_date=date(2000, 1, 1),
        )
        event.collect_events()

        event.update({"title": "After", "notify_days_before": 3}, actor)
        assert event.title == "After"
        assert event.notify_days_before == 3

    def test_update_emits_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        event = Event.create(
            clan_id=uuid.uuid4(),
            actor=actor,
            event_type="birthday",
            title="Test",
            event_date=date(2000, 1, 1),
        )
        event.collect_events()

        event.update({"title": "Updated"}, actor)
        events = event.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], EventUpdated)
        assert events[0].action == "event.update"

    def test_update_rejects_non_whitelisted_field(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        event = Event.create(
            clan_id=uuid.uuid4(),
            actor=actor,
            event_type="birthday",
            title="Test",
            event_date=date(2000, 1, 1),
        )
        event.collect_events()

        with pytest.raises(BusinessRuleViolation, match="field_not_updatable"):
            event.update({"clan_id": uuid.uuid4()}, actor)

    def test_update_rejects_invalid_event_type(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        event = Event.create(
            clan_id=uuid.uuid4(),
            actor=actor,
            event_type="birthday",
            title="Test",
            event_date=date(2000, 1, 1),
        )
        event.collect_events()

        with pytest.raises(BusinessRuleViolation, match="invalid_event_type"):
            event.update({"event_type": "bad_type"}, actor)


# ── Event.delete ─────────────────────────────────────────────────


class TestEventDelete:
    def test_delete_emits_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="admin")
        event = Event.create(
            clan_id=uuid.uuid4(),
            actor=actor,
            event_type="birthday",
            title="Test",
            event_date=date(2000, 1, 1),
        )
        event.collect_events()

        event.delete(actor)
        events = event.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], EventDeleted)
        assert events[0].action == "event.delete"
        assert events[0].resource_id == event.id


# ── EventEvents — auto-populate ──────────────────────────────────


class TestEventEvents:
    def test_created_auto_populates_resource(self) -> None:
        eid = uuid.uuid4()
        e = EventCreated(event_id=eid, clan_id=uuid.uuid4(), actor_id=uuid.uuid4())
        assert e.action == "event.create"
        assert e.resource_type == "event"
        assert e.resource_id == eid

    def test_deleted_auto_populates_resource(self) -> None:
        eid = uuid.uuid4()
        e = EventDeleted(event_id=eid, clan_id=uuid.uuid4(), actor_id=uuid.uuid4())
        assert e.action == "event.delete"
        assert e.resource_id == eid
