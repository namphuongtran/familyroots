"""Clan domain entity — pure Python, no framework dependencies.

The Clan aggregate root owns the clan's own mutable state (profile fields and
active/suspended status) and the business rules that govern changing it. Each
mutation emits a domain event for automatic audit logging, mirroring the Person
aggregate. Membership records (``UserClanRole``) are a separate concern and are
NOT part of this aggregate — changing one member's role must not require loading
the whole clan.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.clan.events import ClanReactivated, ClanSuspended, ClanUpdated
from app.domain.shared.entity import AggregateRoot
from app.domain.shared.exceptions import BusinessRuleViolation
from app.domain.shared.value_objects import ActorInfo

# Profile fields a client may change via update() — exactly the ClanUpdateRequest
# body. Deliberately excludes ``slug`` (identity, not client-editable), ``is_active``
# (only suspend()/reactivate() flip it), and id/timestamps — so update() can never be
# a blind setattr that lets a request reach a field it shouldn't.
_UPDATABLE_FIELDS = frozenset(
    {
        "name",
        "description",
        "origin_place",
        "founded_year",
        "avatar_url",
        "motto",
        "ancestral_hall_location",
        "clan_rules",
    }
)


@dataclass
class Clan(AggregateRoot):
    """Clan aggregate root — a family community's profile and status."""

    name: str = ""
    slug: str = ""
    description: str | None = None
    origin_place: str | None = None
    founded_year: int | None = None
    avatar_url: str | None = None
    is_active: bool = True
    motto: str | None = None
    ancestral_hall_location: str | None = None
    clan_rules: str | None = None

    def update(self, changes: dict[str, object], actor: ActorInfo) -> None:
        """Apply a partial profile update and emit a ClanUpdated event.

        ``changes`` is a dict of field name → new value (only the set fields from
        the Pydantic update schema). A field outside ``_UPDATABLE_FIELDS`` is
        rejected rather than silently written — the single guard against a blind
        setattr reaching id/slug/is_active/timestamps.
        """
        # Validate the whole batch BEFORE mutating anything — a rejected field must
        # not leave earlier fields half-applied (atomic in-memory update).
        invalid = [name for name in changes if name not in _UPDATABLE_FIELDS]
        if invalid:
            raise BusinessRuleViolation("field_not_updatable", {"field": invalid[0]})

        for field_name, new_value in changes.items():
            setattr(self, field_name, new_value)

        self.add_event(
            ClanUpdated(
                clan_id=self.id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                resource_id=self.id,
                changes=dict(changes),
            )
        )

    def suspend(self, actor: ActorInfo) -> None:
        """Deactivate the clan and emit a ClanSuspended event."""
        self.is_active = False
        self.add_event(
            ClanSuspended(
                clan_id=self.id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                resource_id=self.id,
            )
        )

    def reactivate(self, actor: ActorInfo) -> None:
        """Reactivate a suspended clan and emit a ClanReactivated event."""
        self.is_active = True
        self.add_event(
            ClanReactivated(
                clan_id=self.id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                resource_id=self.id,
            )
        )
