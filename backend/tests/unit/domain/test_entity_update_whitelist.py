"""H7 — aggregate update() must whitelist fields and re-assert invariants.

Before the fix, Marriage/ParentChild/Person ``update()`` did a blind ``setattr``
over the changes dict, so a caller could re-point ``created_by_clan_id`` (the edge
ownership / isolation basis), flip ``is_deleted``, or set ``person2_id = person1_id``
(the self-marriage state the constructor forbids). Now only profile fields are
accepted and the construction invariant is re-checked.
"""

import uuid

import pytest

from app.domain.person.entity import Person
from app.domain.relationship.entities import Marriage, ParentChild
from app.domain.shared.exceptions import BusinessRuleViolation
from app.domain.shared.value_objects import ActorInfo


def _actor() -> ActorInfo:
    return ActorInfo.from_jwt({"sub": str(uuid.uuid4())}, "editor")


class TestPersonUpdateWhitelist:
    def test_rejects_non_whitelisted_fields(self) -> None:
        p = Person.create(full_name="A", actor=_actor(), clan_id=uuid.uuid4())
        for bad_field in ("created_by_clan_id", "is_deleted", "created_by", "deleted_at"):
            with pytest.raises(BusinessRuleViolation, match="field_not_updatable"):
                p.update({bad_field: uuid.uuid4()}, _actor(), uuid.uuid4())

    def test_allows_profile_fields(self) -> None:
        p = Person.create(full_name="A", actor=_actor(), clan_id=uuid.uuid4())
        p.update({"full_name": "B", "notes": "x", "phone": "123"}, _actor(), uuid.uuid4())
        assert p.full_name == "B" and p.notes == "x"


class TestMarriageUpdateWhitelist:
    def _marriage(self) -> tuple[Marriage, ActorInfo, uuid.UUID]:
        actor, clan = _actor(), uuid.uuid4()
        m = Marriage.create(
            person1_id=uuid.uuid4(), person2_id=uuid.uuid4(), clan_id=clan, actor=actor
        )
        m.collect_events()
        return m, actor, clan

    def test_rejects_person_and_clan_reassignment(self) -> None:
        m, actor, clan = self._marriage()
        for bad_field in ("person1_id", "person2_id", "created_by_clan_id", "is_deleted"):
            with pytest.raises(BusinessRuleViolation, match="field_not_updatable"):
                m.update({bad_field: uuid.uuid4()}, actor, clan)

    def test_allows_status_and_notes(self) -> None:
        m, actor, clan = self._marriage()
        m.update({"status": "divorced", "notes": "n"}, actor, clan)
        assert m.status == "divorced"


class TestParentChildUpdateWhitelist:
    def test_rejects_edge_reassignment(self) -> None:
        actor, clan = _actor(), uuid.uuid4()
        pc = ParentChild.create(
            parent_id=uuid.uuid4(),
            child_id=uuid.uuid4(),
            clan_id=clan,
            actor=actor,
            relationship_type="biological",
        )
        pc.collect_events()
        for bad_field in ("parent_id", "child_id", "created_by_clan_id"):
            with pytest.raises(BusinessRuleViolation, match="field_not_updatable"):
                pc.update({bad_field: uuid.uuid4()}, actor, clan)

    def test_allows_relationship_type(self) -> None:
        actor, clan = _actor(), uuid.uuid4()
        pc = ParentChild.create(
            parent_id=uuid.uuid4(),
            child_id=uuid.uuid4(),
            clan_id=clan,
            actor=actor,
            relationship_type="biological",
        )
        pc.collect_events()
        pc.update({"relationship_type": "adopted"}, actor, clan)
        assert pc.relationship_type == "adopted"
