"""Unit tests for Branch domain entity and events."""

import uuid

import pytest

from app.domain.branch.entity import Branch
from app.domain.branch.events import BranchCreated, BranchDeleted, BranchUpdated
from app.domain.shared.exceptions import BusinessRuleViolation
from app.domain.shared.value_objects import ActorInfo

# ── Branch.create ────────────────────────────────────────────────


class TestBranchCreate:
    def test_create_sets_fields(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        clan_id = uuid.uuid4()
        branch = Branch.create(
            clan_id=clan_id,
            actor=actor,
            name="Dòng họ chính",
            description="Main lineage branch",
        )
        assert branch.name == "Dòng họ chính"
        assert branch.description == "Main lineage branch"
        assert branch.clan_id == clan_id

    def test_create_emits_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        branch = Branch.create(clan_id=uuid.uuid4(), actor=actor, name="Test Branch")
        events = branch.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], BranchCreated)
        assert events[0].branch_id == branch.id
        assert events[0].action == "branch.create"
        assert events[0].resource_type == "branch"

    def test_create_with_optional_fields(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        founder_id = uuid.uuid4()
        parent_id = uuid.uuid4()
        branch = Branch.create(
            clan_id=uuid.uuid4(),
            actor=actor,
            name="Child Branch",
            founder_person_id=founder_id,
            parent_branch_id=parent_id,
            branch_order=5,
        )
        assert branch.founder_person_id == founder_id
        assert branch.parent_branch_id == parent_id
        assert branch.branch_order == 5


# ── Branch.update ────────────────────────────────────────────────


class TestBranchUpdate:
    def test_update_changes_fields(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        branch = Branch.create(clan_id=uuid.uuid4(), actor=actor, name="Before")
        branch.collect_events()  # drain creation event

        branch.update({"name": "After", "description": "Updated desc"}, actor)
        assert branch.name == "After"
        assert branch.description == "Updated desc"

    def test_update_emits_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        branch = Branch.create(clan_id=uuid.uuid4(), actor=actor, name="Test")
        branch.collect_events()

        branch.update({"name": "Updated"}, actor)
        events = branch.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], BranchUpdated)
        assert events[0].action == "branch.update"

    def test_update_rejects_non_whitelisted_field(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        branch = Branch.create(clan_id=uuid.uuid4(), actor=actor, name="Test")
        branch.collect_events()

        with pytest.raises(BusinessRuleViolation, match="field_not_updatable"):
            branch.update({"clan_id": uuid.uuid4()}, actor)

    def test_update_rejects_self_parent(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="editor")
        branch = Branch.create(clan_id=uuid.uuid4(), actor=actor, name="Test")
        branch.collect_events()

        with pytest.raises(BusinessRuleViolation, match="branch_cannot_be_own_parent"):
            branch.update({"parent_branch_id": branch.id}, actor)


# ── Branch.delete ────────────────────────────────────────────────


class TestBranchDelete:
    def test_delete_emits_event(self) -> None:
        actor = ActorInfo(user_id=uuid.uuid4(), role="admin")
        branch = Branch.create(clan_id=uuid.uuid4(), actor=actor, name="Test")
        branch.collect_events()

        branch.delete(actor)
        events = branch.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], BranchDeleted)
        assert events[0].action == "branch.delete"
        assert events[0].resource_id == branch.id


# ── BranchEvents — auto-populate ─────────────────────────────────


class TestBranchEvents:
    def test_created_auto_populates_resource(self) -> None:
        bid = uuid.uuid4()
        e = BranchCreated(branch_id=bid, clan_id=uuid.uuid4(), actor_id=uuid.uuid4())
        assert e.action == "branch.create"
        assert e.resource_type == "branch"
        assert e.resource_id == bid

    def test_deleted_auto_populates_resource(self) -> None:
        bid = uuid.uuid4()
        e = BranchDeleted(branch_id=bid, clan_id=uuid.uuid4(), actor_id=uuid.uuid4())
        assert e.action == "branch.delete"
        assert e.resource_id == bid
