"""ChangeRequest aggregate: state machine, submit guards, and the merge rule (ADR-037).

The three-way merge in ``detect_conflicts`` is the load-bearing decision of this
feature — it is what stops a week-old suggestion from silently reverting a newer
edit — so it is pinned here at the unit level and again end-to-end over real
Postgres in ``tests/integration/test_change_requests.py``.
"""

from __future__ import annotations

import uuid

import pytest

from app.domain.change_request.entity import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    ChangeRequest,
    validate_person_fields,
    validate_supported,
)
from app.domain.change_request.events import (
    ChangeRequestApproved,
    ChangeRequestRejected,
    ChangeRequestSubmitted,
)
from app.domain.change_request.person_changes import (
    EXCLUDED_PERSON_FIELDS,
    SUBMITTABLE_PERSON_FIELDS,
    detect_conflicts,
)
from app.domain.person.entity import Person
from app.domain.shared.exceptions import BusinessRuleViolation, ConflictError
from app.domain.shared.value_objects import ActorInfo


def _actor(role: str = "viewer") -> ActorInfo:
    return ActorInfo(user_id=uuid.uuid4(), role=role)


def _request(**overrides: object) -> ChangeRequest:
    kwargs: dict[str, object] = {
        "clan_id": uuid.uuid4(),
        "requester": _actor(),
        "person_id": uuid.uuid4(),
        "changes": {"birth_date": "1920-05-03"},
        "base_values": {"birth_date": "1919-01-01", "notes": "unrelated"},
        "base_version": 4,
    }
    kwargs.update(overrides)
    return ChangeRequest.submit_person_update(**kwargs)  # type: ignore[arg-type]


# ── Submittable-field whitelist ──────────────────────────────────────────────


class TestSubmittableFields:
    def test_is_a_strict_subset_of_what_the_person_aggregate_allows(self) -> None:
        """No proposable field may be one the Person aggregate would refuse to set.

        Reads the aggregate's private whitelist deliberately: production code keeps
        its own explicit list (so it never depends on a private name), and THIS is
        the guard that stops the two from drifting apart.
        """
        from app.domain.person.entity import _UPDATABLE_FIELDS

        assert SUBMITTABLE_PERSON_FIELDS < _UPDATABLE_FIELDS

    def test_excludes_exactly_the_documented_fields(self) -> None:
        from app.domain.person.entity import _UPDATABLE_FIELDS

        assert _UPDATABLE_FIELDS - SUBMITTABLE_PERSON_FIELDS == EXCLUDED_PERSON_FIELDS

    def test_contact_pii_is_not_proposable(self) -> None:
        # The review surface echoes the target's CURRENT value for every proposed
        # field; letting phone/email in would leak contact PII into the queue.
        assert "phone" not in SUBMITTABLE_PERSON_FIELDS
        assert "email" not in SUBMITTABLE_PERSON_FIELDS

    def test_every_submittable_field_is_settable_on_a_real_person(self) -> None:
        person = Person.create(full_name="A", actor=_actor("editor"), clan_id=uuid.uuid4())
        person.update(
            {f: None for f in SUBMITTABLE_PERSON_FIELDS if f != "full_name"},
            _actor("editor"),
            uuid.uuid4(),
        )


# ── Submit guards ────────────────────────────────────────────────────────────


class TestSubmitGuards:
    def test_empty_changes_rejected(self) -> None:
        with pytest.raises(BusinessRuleViolation) as exc:
            _request(changes={})
        assert exc.value.code == "change_request.no_changes"

    @pytest.mark.parametrize("bad", ["phone", "email", "avatar_url", "is_deleted", "nonsense"])
    def test_non_submittable_field_rejected(self, bad: str) -> None:
        with pytest.raises(BusinessRuleViolation) as exc:
            _request(changes={bad: "x"})
        assert exc.value.code == "change_request.field_not_submittable"
        assert exc.value.detail["fields"] == [bad]

    @pytest.mark.parametrize(
        ("action", "resource_type"),
        [
            ("create", "person"),
            ("delete", "person"),
            ("update", "marriage"),
            ("update", "event"),
            ("update", "document"),
            ("update", "parent_child"),
        ],
    )
    def test_only_person_update_is_executed_by_this_build(
        self, action: str, resource_type: str
    ) -> None:
        with pytest.raises(BusinessRuleViolation) as exc:
            validate_supported(action, resource_type)
        assert exc.value.code == "change_request.unsupported_operation"

    def test_person_update_is_supported(self) -> None:
        validate_supported("update", "person")  # does not raise

    def test_validate_person_fields_accepts_a_normal_correction(self) -> None:
        validate_person_fields({"birth_date": "1920-05-03", "birth_place": "Nam Định"})

    def test_base_values_are_narrowed_to_the_proposed_fields(self) -> None:
        """A full row copy would be a second, staler mirror of the person record."""
        cr = _request()
        assert set(cr.base_values) == {"birth_date"}

    def test_submission_emits_an_auditable_event(self) -> None:
        cr = _request(changes={"birth_date": "1920-05-03", "notes": "n"})
        (event,) = cr.collect_events()
        assert isinstance(event, ChangeRequestSubmitted)
        assert event.action == "change_request.submit"
        assert event.resource_type == "change_request"
        assert event.resource_id == cr.id
        assert event.new_value is not None
        assert event.new_value["fields"] == ["birth_date", "notes"]


# ── Review state machine ─────────────────────────────────────────────────────


class TestReviewTransitions:
    def test_approve_records_reviewer_and_emits_event(self) -> None:
        cr = _request()
        cr.collect_events()
        reviewer = _actor("editor")

        cr.approve(reviewer, applied_version=9, review_notes="đúng rồi")

        assert cr.status == STATUS_APPROVED
        assert cr.reviewed_by == reviewer.user_id
        assert cr.reviewed_at is not None
        assert cr.review_notes == "đúng rồi"
        (event,) = cr.collect_events()
        assert isinstance(event, ChangeRequestApproved)
        assert event.action == "change_request.approve"
        assert event.actor_id == reviewer.user_id
        assert event.new_value is not None
        # The audit row shows both what the proposal was written against and what it
        # actually landed on — the merge is reconstructable after the fact.
        assert event.new_value["base_version"] == 4
        assert event.new_value["applied_version"] == 9

    def test_reject_records_reviewer_and_emits_event(self) -> None:
        cr = _request()
        cr.collect_events()
        reviewer = _actor("admin")

        cr.reject(reviewer, review_notes="sai nguồn")

        assert cr.status == STATUS_REJECTED
        assert cr.reviewed_by == reviewer.user_id
        (event,) = cr.collect_events()
        assert isinstance(event, ChangeRequestRejected)
        assert event.action == "change_request.reject"

    @pytest.mark.parametrize("first", ["approve", "reject"])
    @pytest.mark.parametrize("second", ["approve", "reject"])
    def test_a_reviewed_request_cannot_be_reviewed_again(self, first: str, second: str) -> None:
        cr = _request()
        getattr(cr, first)(_actor("editor"))
        with pytest.raises(ConflictError) as exc:
            getattr(cr, second)(_actor("admin"))
        assert exc.value.code == "change_request.not_pending"

    def test_starts_pending(self) -> None:
        assert _request().status == STATUS_PENDING


# ── The merge rule ───────────────────────────────────────────────────────────


class TestDetectConflicts:
    def test_untouched_field_is_applicable(self) -> None:
        conflicts = detect_conflicts(
            changes={"birth_date": "1920-05-03"},
            base_values={"birth_date": "1919-01-01"},
            current_values={"birth_date": "1919-01-01"},
        )
        assert conflicts == []

    def test_someone_else_wrote_a_different_value_is_a_conflict(self) -> None:
        conflicts = detect_conflicts(
            changes={"birth_date": "1920-05-03"},
            base_values={"birth_date": "1919-01-01"},
            current_values={"birth_date": "1921-12-31"},
        )
        assert [c.field for c in conflicts] == ["birth_date"]
        (conflict,) = conflicts
        assert conflict.as_dict() == {
            "field": "birth_date",
            "base": "1919-01-01",
            "current": "1921-12-31",
            "proposed": "1920-05-03",
        }

    def test_someone_else_already_made_this_exact_correction_is_not_a_conflict(self) -> None:
        """Re-applying an identical value is a no-op, not a lost update."""
        conflicts = detect_conflicts(
            changes={"birth_date": "1920-05-03"},
            base_values={"birth_date": "1919-01-01"},
            current_values={"birth_date": "1920-05-03"},
        )
        assert conflicts == []

    def test_movement_on_a_field_this_request_does_not_touch_is_irrelevant(self) -> None:
        """The whole point of merging per field: a birth-date fix survives a bio rewrite."""
        conflicts = detect_conflicts(
            changes={"birth_date": "1920-05-03"},
            base_values={"birth_date": "1919-01-01"},
            current_values={"birth_date": "1919-01-01", "biography": "rewritten"},
        )
        assert conflicts == []

    def test_reports_every_conflicting_field_not_just_the_first(self) -> None:
        conflicts = detect_conflicts(
            changes={"birth_date": "1920-05-03", "birth_place": "Nam Định", "notes": "n"},
            base_values={"birth_date": "1919-01-01", "birth_place": "Hà Nội", "notes": None},
            current_values={"birth_date": "1921-12-31", "birth_place": "Huế", "notes": None},
        )
        assert sorted(c.field for c in conflicts) == ["birth_date", "birth_place"]

    def test_none_is_a_real_value_on_both_sides(self) -> None:
        # base None -> current "x" while proposing None: a real conflict (clearing a
        # field someone just filled in).
        conflicts = detect_conflicts(
            changes={"notes": None},
            base_values={"notes": None},
            current_values={"notes": "someone wrote this"},
        )
        assert [c.field for c in conflicts] == ["notes"]

    def test_conflicts_against_uses_the_aggregates_own_snapshot(self) -> None:
        cr = _request()
        assert cr.conflicts_against({"birth_date": "1919-01-01"}) == []
        assert [c.field for c in cr.conflicts_against({"birth_date": "1955-01-01"})] == [
            "birth_date"
        ]
