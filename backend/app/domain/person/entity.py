"""Person domain entity — pure Python, no framework dependencies.

The Person aggregate root encapsulates all business rules related to
person management: creating, updating, soft-deleting, and restoring.
Each mutation emits a domain event for automatic audit logging.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.domain.person.events import (
    PersonCreated,
    PersonDeleted,
    PersonRestored,
    PersonUpdated,
)
from app.domain.shared.entity import AggregateRoot
from app.domain.shared.exceptions import BusinessRuleViolation
from app.domain.shared.value_objects import ActorInfo

# Profile fields a client may change via update() (mirrors the PersonUpdate schema).
# Excludes created_by_clan_id (origin/isolation), soft-delete, and audit columns —
# those are set only by create()/soft_delete()/restore(), never a blind setattr.
_UPDATABLE_FIELDS = frozenset(
    {
        "full_name",
        "birth_name",
        "courtesy_name",
        "posthumous_name",
        "alias_name",
        "gender",
        "birth_date",
        "birth_date_precision",
        "birth_date_display",
        "death_date",
        "death_date_precision",
        "death_date_display",
        "lunar_birth_date",
        "lunar_death_date",
        "birth_place",
        "death_place",
        "burial_place",
        "tomb_location",
        "residence_place",
        "religion",
        "nationality",
        "occupation",
        "education_level",
        "title_rank",
        "phone",
        "email",
        "biography",
        "notes",
    }
)

# avatar_url is deliberately ABSENT from _UPDATABLE_FIELDS (ADR-036). It is
# server-managed: the only writer is set_avatar_url(), called by the set-avatar use
# case with a URL the backend itself just published into the public avatars bucket.
# A client-supplied value would let anyone point a member's portrait at an arbitrary
# host — an SSRF/tracking-pixel/moderation surface that "permanent public URL" never
# implied — so update() raises field_not_updatable for it like any other
# non-updatable column.

# The persons.avatar_url column is varchar(500); the domain owns the number so the
# invariant is checked before the driver can raise a truncation error.
AVATAR_URL_MAX_LENGTH = 500


@dataclass
class Person(AggregateRoot):
    """Person aggregate root.

    Represents an individual in the genealogy system. A Person may belong
    to multiple clans via ClanMembership links, but the entity itself is
    clan-independent.
    """

    # ── Identity ──────────────────────────────────────────────
    full_name: str = ""
    birth_name: str | None = None
    courtesy_name: str | None = None
    posthumous_name: str | None = None
    alias_name: str | None = None
    gender: str = "unknown"

    # ── Dates (solar) ─────────────────────────────────────────
    birth_date: date | None = None
    birth_date_precision: str = "exact"
    birth_date_display: str | None = None
    death_date: date | None = None
    death_date_precision: str = "exact"
    death_date_display: str | None = None

    # ── Dates (lunar — display only) ──────────────────────────
    lunar_birth_date: str | None = None
    lunar_death_date: str | None = None

    # ── Places ────────────────────────────────────────────────
    birth_place: str | None = None
    death_place: str | None = None
    burial_place: str | None = None
    tomb_location: str | None = None
    residence_place: str | None = None

    # ── Personal info ─────────────────────────────────────────
    religion: str | None = None
    nationality: str = "VN"
    occupation: str | None = None
    education_level: str | None = None
    title_rank: str | None = None
    phone: str | None = None
    email: str | None = None

    # ── Content ───────────────────────────────────────────────
    biography: str | None = None
    avatar_url: str | None = None
    notes: str | None = None

    # ── Origin ────────────────────────────────────────────────
    created_by_clan_id: uuid.UUID | None = None

    # ── Soft delete ───────────────────────────────────────────
    is_deleted: bool = False
    deleted_at: datetime | None = None
    deleted_by: uuid.UUID | None = None

    # ── Audit ─────────────────────────────────────────────────
    created_by: uuid.UUID = field(default_factory=uuid.uuid4)
    updated_by: uuid.UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Optimistic concurrency (ADR-017). Not client-updatable; the repository
    # bumps it on every successful UPDATE.
    version: int = 1

    # ── Domain methods ────────────────────────────────────────

    @classmethod
    def create(
        cls,
        *,
        full_name: str,
        actor: ActorInfo,
        clan_id: uuid.UUID,
        **kwargs: Any,
    ) -> Person:
        """Factory method to create a new Person with a creation event."""
        if "avatar_url" in kwargs:
            # Backstop for the create path, which does not go through
            # _UPDATABLE_FIELDS. avatar_url is server-managed (ADR-036) — the only
            # writer is set_avatar_url(), after the backend has published the image.
            raise BusinessRuleViolation("field_not_updatable", {"field": "avatar_url"})
        person = cls(
            full_name=full_name,
            created_by=actor.user_id,
            **kwargs,
        )
        person._validate_dates()
        person.add_event(
            PersonCreated(
                person_id=person.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                full_name=full_name,
            )
        )
        return person

    def update(self, changes: dict[str, object], actor: ActorInfo, clan_id: uuid.UUID) -> None:
        """Apply a partial update and emit a PersonUpdated event.

        ``changes`` is a dict of field name → new value (only non-None
        values from the Pydantic update schema).
        """
        old_values: dict[str, object] = {}
        for field_name, new_value in changes.items():
            if field_name not in _UPDATABLE_FIELDS:
                raise BusinessRuleViolation("field_not_updatable", {"field": field_name})
            old_values[field_name] = getattr(self, field_name, None)
            setattr(self, field_name, new_value)

        self._validate_dates()
        self.updated_by = actor.user_id
        self.updated_at = datetime.now(UTC)

        self.add_event(
            PersonUpdated(
                person_id=self.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                changes=changes,
                old_values=old_values,
            )
        )

    def set_avatar_url(self, url: str, actor: ActorInfo, clan_id: uuid.UUID) -> None:
        """Stamp the person's permanent, publicly-fetchable avatar URL (ADR-036).

        Server-only: the set-avatar use case calls this with a URL the backend has
        just published into the public avatars bucket. Clients cannot reach it —
        ``avatar_url`` is not in ``_UPDATABLE_FIELDS`` and is rejected by the request
        schema.

        The invariant enforced here is **durability**: the stored value must be an
        absolute http(s) URL with no query string and no fragment. Every presigned
        URL carries its signature and expiry in the query string, so this
        structurally excludes them — the column cannot come to hold a URL that
        quietly stops resolving an hour (or thirty days) later, which is the exact
        failure this decision exists to prevent. The rule is expressed in terms of
        URL *shape*, not of any provider's URL format, so it stays framework- and
        vendor-agnostic like the rest of the domain.

        Emits ``PersonUpdated`` so the change is audited like any other field edit.
        """
        cleaned = (url or "").strip()
        if (
            not cleaned
            or not cleaned.startswith(("https://", "http://"))
            or len(cleaned) > AVATAR_URL_MAX_LENGTH
        ):
            raise BusinessRuleViolation(
                "person.avatar_url_invalid", detail={"max_length": AVATAR_URL_MAX_LENGTH}
            )
        if "?" in cleaned or "#" in cleaned:
            raise BusinessRuleViolation("person.avatar_url_not_permanent")

        old_value = self.avatar_url
        self.avatar_url = cleaned
        self.updated_by = actor.user_id
        self.updated_at = datetime.now(UTC)
        self.add_event(
            PersonUpdated(
                person_id=self.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
                changes={"avatar_url": cleaned},
                old_values={"avatar_url": old_value},
            )
        )

    def _validate_dates(self) -> None:
        """Reject an impossible lifespan (death before birth).

        Called from the write paths (create/update) ONLY — deliberately NOT in
        __post_init__, because the persistence mapper reconstructs Person from every DB
        row and must not raise on pre-existing rows that predate this rule. This is the
        single source of truth for the cross-field rule (the API schema does not
        duplicate it), so it also covers partial PATCH updates. Date precision is
        intentionally ignored — death before birth is impossible regardless of how
        precisely either date is known.
        """
        if self.birth_date and self.death_date and self.death_date < self.birth_date:
            raise BusinessRuleViolation(
                "person.death_before_birth",
                detail={"birth_date": str(self.birth_date), "death_date": str(self.death_date)},
            )

    def soft_delete(self, actor: ActorInfo, clan_id: uuid.UUID) -> None:
        """Mark the person as soft-deleted."""
        self.is_deleted = True
        self.deleted_at = datetime.now(UTC)
        self.deleted_by = actor.user_id

        self.add_event(
            PersonDeleted(
                person_id=self.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
            )
        )

    def restore(self, actor: ActorInfo, clan_id: uuid.UUID) -> None:
        """Restore a soft-deleted person."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None

        self.add_event(
            PersonRestored(
                person_id=self.id,
                clan_id=clan_id,
                actor_id=actor.user_id,
                actor_role=actor.role,
            )
        )
