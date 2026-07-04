"""Unit tests for Relationship domain entities, events, and validator."""

import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.domain.relationship.entities import Marriage, ParentChild
from app.domain.relationship.events import (
    MarriageCreated,
    MarriageDeleted,
    ParentChildCreated,
    ParentChildDeleted,
)
from app.domain.relationship.validator import RelationshipDomainValidator
from app.domain.shared.exceptions import BusinessRuleViolation, ConflictError
from app.domain.shared.value_objects import ActorInfo

# ── Marriage entity ──────────────────────────────────────────────


class TestMarriage:
    def test_create_emits_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        clan_id = uuid.uuid4()
        p1, p2 = uuid.uuid4(), uuid.uuid4()
        m = Marriage.create(person1_id=p1, person2_id=p2, clan_id=clan_id, actor=actor)
        events = m.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], MarriageCreated)
        assert events[0].action == "marriage.create"

    def test_self_marriage_raises(self) -> None:
        pid = uuid.uuid4()
        with pytest.raises(BusinessRuleViolation, match="self_marriage_not_allowed"):
            Marriage(person1_id=pid, person2_id=pid)

    def test_soft_delete_emits_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="admin")
        clan_id = uuid.uuid4()
        m = Marriage.create(
            person1_id=uuid.uuid4(),
            person2_id=uuid.uuid4(),
            clan_id=clan_id,
            actor=actor,
        )
        m.collect_events()  # drain
        m.soft_delete(actor, clan_id)
        events = m.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], MarriageDeleted)
        assert m.is_deleted is True


# ── ParentChild entity ───────────────────────────────────────────


class TestParentChild:
    def test_create_emits_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        clan_id = uuid.uuid4()
        link = ParentChild.create(
            parent_id=uuid.uuid4(),
            child_id=uuid.uuid4(),
            clan_id=clan_id,
            actor=actor,
        )
        events = link.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], ParentChildCreated)
        assert events[0].action == "parent_child.create"

    def test_self_parent_raises(self) -> None:
        pid = uuid.uuid4()
        with pytest.raises(BusinessRuleViolation, match="self_parent_not_allowed"):
            ParentChild(parent_id=pid, child_id=pid)

    def test_soft_delete_emits_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="admin")
        clan_id = uuid.uuid4()
        link = ParentChild.create(
            parent_id=uuid.uuid4(),
            child_id=uuid.uuid4(),
            clan_id=clan_id,
            actor=actor,
        )
        link.collect_events()
        link.soft_delete(actor, clan_id)
        events = link.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], ParentChildDeleted)


# ── Domain Validator ─────────────────────────────────────────────


class TestRelationshipDomainValidator:
    def _make_validator(self, **overrides: object) -> RelationshipDomainValidator:
        query_port = AsyncMock()
        query_port.count_bio_parents = AsyncMock(return_value=0)
        query_port.has_active_marriage = AsyncMock(return_value=False)
        query_port.has_parent_child_link = AsyncMock(return_value=False)
        query_port.is_ancestor = AsyncMock(return_value=False)
        query_port.get_birth_dates = AsyncMock(return_value={})
        for k, v in overrides.items():
            setattr(query_port, k, AsyncMock(return_value=v))
        return RelationshipDomainValidator(query_port)

    @pytest.mark.asyncio
    async def test_self_parent_raises(self) -> None:
        v = self._make_validator()
        pid = uuid.uuid4()
        with pytest.raises(BusinessRuleViolation, match="self_parent_not_allowed"):
            await v.validate_parent_child(pid, pid, "biological", uuid.uuid4())

    @pytest.mark.asyncio
    async def test_too_many_bio_parents_raises(self) -> None:
        v = self._make_validator(count_bio_parents=2)
        with pytest.raises(ConflictError, match="too_many_biological_parents"):
            await v.validate_parent_child(uuid.uuid4(), uuid.uuid4(), "biological", uuid.uuid4())

    @pytest.mark.asyncio
    async def test_parent_too_young_raises(self) -> None:
        parent_id, child_id = uuid.uuid4(), uuid.uuid4()
        v = self._make_validator(
            get_birth_dates={parent_id: date(2000, 1, 1), child_id: date(2005, 1, 1)},
        )
        with pytest.raises(BusinessRuleViolation, match="parent_too_young"):
            await v.validate_parent_child(parent_id, child_id, "biological", uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cycle_detection_raises(self) -> None:
        v = self._make_validator(is_ancestor=True)
        with pytest.raises(BusinessRuleViolation, match="creates_cycle"):
            await v.validate_parent_child(uuid.uuid4(), uuid.uuid4(), "biological", uuid.uuid4())

    @pytest.mark.asyncio
    async def test_duplicate_marriage_raises(self) -> None:
        v = self._make_validator(has_active_marriage=True)
        with pytest.raises(ConflictError, match="duplicate_marriage"):
            await v.check_duplicate_marriage(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_duplicate_parent_child_raises(self) -> None:
        v = self._make_validator(has_parent_child_link=True)
        with pytest.raises(ConflictError, match="duplicate_parent_child"):
            await v.check_duplicate_parent_child(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_valid_parent_child_passes(self) -> None:
        v = self._make_validator()
        result = await v.validate_parent_child(
            uuid.uuid4(), uuid.uuid4(), "biological", uuid.uuid4()
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_unusual_age_gap_returns_warning(self) -> None:
        parent_id, child_id = uuid.uuid4(), uuid.uuid4()
        v = self._make_validator(
            get_birth_dates={parent_id: date(1900, 1, 1), child_id: date(1990, 1, 1)},
        )
        result = await v.validate_parent_child(parent_id, child_id, "biological", uuid.uuid4())
        assert result is not None
        assert "warning" in result
