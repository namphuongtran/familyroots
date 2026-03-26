"""Mapper between Branch domain entity and SQLAlchemy ORM model.

Keeps the domain layer free of SQLAlchemy imports by providing
explicit conversion functions.
"""

from __future__ import annotations

from app.domain.branch.entity import Branch as BranchEntity
from app.models.branch import Branch as BranchModel

_MAPPED_FIELDS = (
    "clan_id",
    "name",
    "description",
    "founder_person_id",
    "parent_branch_id",
    "branch_order",
)


def to_domain(model: BranchModel) -> BranchEntity:
    """Convert a SQLAlchemy Branch ORM instance to a domain entity."""
    return BranchEntity(
        id=model.id,
        clan_id=model.clan_id,
        name=model.name,
        description=model.description,
        founder_person_id=model.founder_person_id,
        parent_branch_id=model.parent_branch_id,
        branch_order=model.branch_order,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def to_orm(entity: BranchEntity) -> BranchModel:
    """Convert a domain Branch entity to a SQLAlchemy ORM instance (INSERT)."""
    return BranchModel(
        id=entity.id,
        clan_id=entity.clan_id,
        name=entity.name,
        description=entity.description,
        founder_person_id=entity.founder_person_id,
        parent_branch_id=entity.parent_branch_id,
        branch_order=entity.branch_order,
    )


def apply_to_orm(entity: BranchEntity, model: BranchModel) -> None:
    """Apply domain entity state onto an existing ORM model (UPDATE)."""
    for field_name in _MAPPED_FIELDS:
        setattr(model, field_name, getattr(entity, field_name))
