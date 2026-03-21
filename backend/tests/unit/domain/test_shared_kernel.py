"""Unit tests for the shared domain kernel.

Tests cover:
- Entity identity
- AggregateRoot event collection and draining
- Value objects construction
- Domain exception hierarchy
"""

import uuid

import pytest

from app.domain.shared.entity import AggregateRoot, Entity
from app.domain.shared.events import AuditableEvent, DomainEvent
from app.domain.shared.exceptions import (
    BusinessRuleViolation,
    ConflictError,
    DomainError,
    EntityNotFoundError,
    ForbiddenError,
)
from app.domain.shared.value_objects import ActorInfo, ClanScope


# ── Entity ──────────────────────────────────────────────────────


class TestEntity:
    def test_auto_uuid(self) -> None:
        """Entity generates a unique UUID by default."""
        e1 = Entity()
        e2 = Entity()
        assert isinstance(e1.id, uuid.UUID)
        assert e1.id != e2.id

    def test_explicit_id(self) -> None:
        """Entity accepts an explicit UUID."""
        fixed_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        e = Entity(id=fixed_id)
        assert e.id == fixed_id


# ── AggregateRoot ───────────────────────────────────────────────


class TestAggregateRoot:
    def test_add_and_collect_events(self) -> None:
        """Events added via add_event are returned by collect_events."""
        agg = AggregateRoot()
        event1 = DomainEvent()
        event2 = DomainEvent()
        agg.add_event(event1)
        agg.add_event(event2)

        events = agg.collect_events()
        assert len(events) == 2
        assert events[0] is event1
        assert events[1] is event2

    def test_collect_events_drains(self) -> None:
        """collect_events clears the internal buffer after draining."""
        agg = AggregateRoot()
        agg.add_event(DomainEvent())
        agg.collect_events()

        # Second call should return empty list
        assert agg.collect_events() == []

    def test_no_events_initially(self) -> None:
        """A freshly created aggregate has no events."""
        agg = AggregateRoot()
        assert agg.collect_events() == []


# ── DomainEvent ─────────────────────────────────────────────────


class TestDomainEvent:
    def test_occurs_at_auto_set(self) -> None:
        """DomainEvent automatically records occurred_at."""
        event = DomainEvent()
        assert event.occurred_at is not None

    def test_event_id_auto_generated(self) -> None:
        """Each event gets a unique event_id."""
        e1 = DomainEvent()
        e2 = DomainEvent()
        assert e1.event_id != e2.event_id

    def test_event_is_frozen(self) -> None:
        """DomainEvent is immutable."""
        event = DomainEvent()
        with pytest.raises(AttributeError):
            event.occurred_at = None  # type: ignore[misc]


# ── AuditableEvent ──────────────────────────────────────────────


class TestAuditableEvent:
    def test_carries_audit_data(self) -> None:
        """AuditableEvent carries all fields needed for an audit log entry."""
        clan = uuid.uuid4()
        actor = uuid.uuid4()
        resource = uuid.uuid4()
        event = AuditableEvent(
            clan_id=clan,
            actor_id=actor,
            actor_role="editor",
            action="person.create",
            resource_type="person",
            resource_id=resource,
        )
        assert event.clan_id == clan
        assert event.actor_id == actor
        assert event.actor_role == "editor"
        assert event.action == "person.create"
        assert event.resource_type == "person"
        assert event.resource_id == resource

    def test_inherits_domain_event(self) -> None:
        """AuditableEvent is a DomainEvent."""
        event = AuditableEvent()
        assert isinstance(event, DomainEvent)


# ── Value Objects ───────────────────────────────────────────────


class TestActorInfo:
    def test_from_jwt(self) -> None:
        uid = uuid.uuid4()
        actor = ActorInfo.from_jwt({"sub": str(uid)}, "admin")
        assert actor.user_id == uid
        assert actor.role == "admin"

    def test_frozen(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        with pytest.raises(AttributeError):
            actor.role = "admin"  # type: ignore[misc]


class TestClanScope:
    def test_wraps_clan_id(self) -> None:
        cid = uuid.uuid4()
        scope = ClanScope(clan_id=cid)
        assert scope.clan_id == cid

    def test_frozen(self) -> None:
        scope = ClanScope(clan_id=uuid.uuid4())
        with pytest.raises(AttributeError):
            scope.clan_id = uuid.uuid4()  # type: ignore[misc]


# ── Domain Exceptions ───────────────────────────────────────────


class TestDomainExceptions:
    def test_hierarchy(self) -> None:
        """All domain exceptions inherit from DomainError."""
        assert issubclass(EntityNotFoundError, DomainError)
        assert issubclass(BusinessRuleViolation, DomainError)
        assert issubclass(ConflictError, DomainError)
        assert issubclass(ForbiddenError, DomainError)

    def test_error_code(self) -> None:
        exc = EntityNotFoundError("person_not_found")
        assert exc.code == "person_not_found"
        assert exc.detail == {}

    def test_error_detail(self) -> None:
        exc = BusinessRuleViolation(
            "parent_too_young",
            detail={"min_age_gap": 12},
        )
        assert exc.code == "parent_too_young"
        assert exc.detail == {"min_age_gap": 12}

    def test_str_representation(self) -> None:
        """String representation uses the error code."""
        exc = ConflictError("duplicate_marriage")
        assert str(exc) == "duplicate_marriage"
