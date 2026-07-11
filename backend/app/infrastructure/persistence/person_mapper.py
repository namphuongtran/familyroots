"""Mapper between Person domain entity and SQLAlchemy ORM model.

Keeps the domain layer free of SQLAlchemy imports by providing
explicit conversion functions.
"""

from __future__ import annotations

from app.domain.person.entity import Person as PersonEntity
from app.models.person import Person as PersonModel


def to_domain(model: PersonModel) -> PersonEntity:
    """Convert a SQLAlchemy Person ORM instance to a domain entity."""
    return PersonEntity(
        id=model.id,
        full_name=model.full_name,
        birth_name=model.birth_name,
        courtesy_name=model.courtesy_name,
        posthumous_name=model.posthumous_name,
        alias_name=model.alias_name,
        gender=model.gender,
        birth_date=model.birth_date,
        birth_date_precision=model.birth_date_precision,
        birth_date_display=model.birth_date_display,
        death_date=model.death_date,
        death_date_precision=model.death_date_precision,
        death_date_display=model.death_date_display,
        lunar_birth_date=model.lunar_birth_date,
        lunar_death_date=model.lunar_death_date,
        birth_place=model.birth_place,
        death_place=model.death_place,
        burial_place=model.burial_place,
        tomb_location=model.tomb_location,
        residence_place=model.residence_place,
        religion=model.religion,
        nationality=model.nationality,
        occupation=model.occupation,
        education_level=model.education_level,
        title_rank=model.title_rank,
        phone=model.phone,
        email=model.email,
        biography=model.biography,
        avatar_url=model.avatar_url,
        notes=model.notes,
        created_by_clan_id=model.created_by_clan_id,
        is_deleted=model.is_deleted,
        deleted_at=model.deleted_at,
        deleted_by=model.deleted_by,
        created_by=model.created_by,
        updated_by=model.updated_by,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def to_orm(entity: PersonEntity) -> PersonModel:
    """Convert a domain Person entity to a SQLAlchemy ORM instance.

    Used for INSERT operations. For UPDATE, use ``apply_to_orm`` instead.
    """
    return PersonModel(
        id=entity.id,
        full_name=entity.full_name,
        birth_name=entity.birth_name,
        courtesy_name=entity.courtesy_name,
        posthumous_name=entity.posthumous_name,
        alias_name=entity.alias_name,
        gender=entity.gender,
        birth_date=entity.birth_date,
        birth_date_precision=entity.birth_date_precision,
        birth_date_display=entity.birth_date_display,
        death_date=entity.death_date,
        death_date_precision=entity.death_date_precision,
        death_date_display=entity.death_date_display,
        lunar_birth_date=entity.lunar_birth_date,
        lunar_death_date=entity.lunar_death_date,
        birth_place=entity.birth_place,
        death_place=entity.death_place,
        burial_place=entity.burial_place,
        tomb_location=entity.tomb_location,
        residence_place=entity.residence_place,
        religion=entity.religion,
        nationality=entity.nationality,
        occupation=entity.occupation,
        education_level=entity.education_level,
        title_rank=entity.title_rank,
        phone=entity.phone,
        email=entity.email,
        biography=entity.biography,
        avatar_url=entity.avatar_url,
        notes=entity.notes,
        created_by_clan_id=entity.created_by_clan_id,
        is_deleted=entity.is_deleted,
        deleted_at=entity.deleted_at,
        deleted_by=entity.deleted_by,
        created_by=entity.created_by,
        updated_by=entity.updated_by,
    )


UPDATABLE_FIELDS = (
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
    "avatar_url",
    "notes",
    # created_by_clan_id is intentionally NOT updatable: it is provenance and the
    # claim-authorization path keys on it (reassigning it = cross-clan escalation).
    "is_deleted",
    "deleted_at",
    "deleted_by",
    "updated_by",
)


def apply_to_orm(entity: PersonEntity, model: PersonModel) -> None:
    """Apply domain entity state onto an existing ORM model (for UPDATE).

    Only copies fields listed in ``UPDATABLE_FIELDS`` to avoid
    touching primary keys, timestamps, or ORM relationships.
    """
    for field_name in UPDATABLE_FIELDS:
        setattr(model, field_name, getattr(entity, field_name))
