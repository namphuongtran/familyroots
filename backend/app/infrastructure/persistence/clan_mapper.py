"""Mapper between the Clan domain entity and its SQLAlchemy ORM model.

Keeps the domain layer free of SQLAlchemy by providing explicit conversions.
"""

from __future__ import annotations

from app.domain.clan.entity import Clan as ClanEntity
from app.models.clan import Clan as ClanModel


def to_domain(model: ClanModel) -> ClanEntity:
    """Convert a SQLAlchemy Clan ORM instance to a domain entity."""
    return ClanEntity(
        id=model.id,
        name=model.name,
        slug=model.slug,
        description=model.description,
        origin_place=model.origin_place,
        founded_year=model.founded_year,
        avatar_url=model.avatar_url,
        is_active=model.is_active,
        motto=model.motto,
        ancestral_hall_location=model.ancestral_hall_location,
        clan_rules=model.clan_rules,
    )


# Fields copied domain → ORM on UPDATE. Includes ``is_active`` (suspend/reactivate set
# it) but NOT ``slug``/``id``/timestamps — those are never mutated through the aggregate.
UPDATABLE_FIELDS = (
    "name",
    "description",
    "origin_place",
    "founded_year",
    "avatar_url",
    "is_active",
    "motto",
    "ancestral_hall_location",
    "clan_rules",
)


def apply_to_orm(entity: ClanEntity, model: ClanModel) -> None:
    """Apply domain entity state onto an existing ORM model (for UPDATE)."""
    for field_name in UPDATABLE_FIELDS:
        setattr(model, field_name, getattr(entity, field_name))
