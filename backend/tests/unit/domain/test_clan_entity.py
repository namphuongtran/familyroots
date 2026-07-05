"""L12: the Clan aggregate owns its mutation rules.

update() enforces a field whitelist (so a request can never blind-setattr id/slug/
is_active/timestamps), and every mutation emits its own domain event. Before L12 the
handler called repo.update_clan() which did a bare setattr loop over the change dict.
"""

import uuid

import pytest

from app.domain.clan.entity import Clan
from app.domain.clan.events import ClanReactivated, ClanSuspended, ClanUpdated
from app.domain.shared.exceptions import BusinessRuleViolation
from app.domain.shared.value_objects import ActorInfo

pytestmark = [pytest.mark.unit]


def _actor() -> ActorInfo:
    return ActorInfo(user_id=uuid.uuid4(), role="admin")


def _clan() -> Clan:
    return Clan(name="Nguyen", slug="nguyen", is_active=True)


def test_update_applies_whitelisted_fields_and_emits_event() -> None:
    clan = _clan()
    actor = _actor()

    clan.update({"name": "Trần", "motto": "Kính tổ"}, actor)

    assert clan.name == "Trần"
    assert clan.motto == "Kính tổ"
    events = clan.collect_events()
    assert len(events) == 1
    assert isinstance(events[0], ClanUpdated)
    assert events[0].changes == {"name": "Trần", "motto": "Kính tổ"}
    assert events[0].actor_id == actor.user_id


@pytest.mark.parametrize("bad_field", ["is_active", "slug", "id", "created_at", "founded_year_x"])
def test_update_rejects_non_whitelisted_field(bad_field: str) -> None:
    """The guard against a blind setattr: fields outside the whitelist are refused.

    A revert to the old bare setattr loop would apply these silently and NOT raise,
    failing this test."""
    clan = _clan()
    with pytest.raises(BusinessRuleViolation, match="field_not_updatable"):
        clan.update({bad_field: "x"}, _actor())
    # nothing was emitted because the mutation was rejected
    assert clan.collect_events() == []


def test_update_rejection_is_atomic_no_partial_write() -> None:
    """A rejected field must not leave earlier fields in the batch mutated."""
    clan = _clan()
    original = clan.name
    with pytest.raises(BusinessRuleViolation):
        # 'name' is valid, 'is_active' is not — the whole call must fail
        clan.update({"name": "Changed", "is_active": False}, _actor())
    # neither field mutated: validation runs before any setattr
    assert clan.name == original
    assert clan.is_active is True


def test_suspend_and_reactivate_flip_flag_and_emit_events() -> None:
    clan = _clan()
    actor = _actor()

    clan.suspend(actor)
    assert clan.is_active is False
    suspended = clan.collect_events()
    assert len(suspended) == 1
    assert isinstance(suspended[0], ClanSuspended)
    assert suspended[0].action == "clan.suspend"

    clan.reactivate(actor)
    assert clan.is_active is True
    reactivated = clan.collect_events()
    assert len(reactivated) == 1
    assert isinstance(reactivated[0], ClanReactivated)
    assert reactivated[0].action == "clan.reactivate"
