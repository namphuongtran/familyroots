"""Mapper between Document domain entity and SQLAlchemy ORM model."""

from __future__ import annotations

from app.domain.document.entity import Document as DocumentEntity
from app.models.document import Document as DocumentModel

_MAPPED_FIELDS = (
    "clan_id",
    "person_id",
    "title",
    "description",
    "document_type",
    "storage_path",
    "file_size_bytes",
    "mime_type",
    "original_filename",
    "taken_date",
    "taken_place",
    "is_avatar",
    "created_by",
    "is_deleted",
    "deleted_at",
    "deleted_by",
)


def to_domain(model: DocumentModel) -> DocumentEntity:
    """Convert a SQLAlchemy Document ORM instance to a domain entity."""
    return DocumentEntity(
        id=model.id,
        clan_id=model.clan_id,
        person_id=model.person_id,
        title=model.title,
        description=model.description,
        document_type=model.document_type,
        storage_path=model.storage_path,
        file_size_bytes=model.file_size_bytes,
        mime_type=model.mime_type,
        original_filename=model.original_filename,
        taken_date=model.taken_date,
        taken_place=model.taken_place,
        is_avatar=model.is_avatar,
        created_by=model.created_by,
        created_at=model.created_at,
        updated_at=model.updated_at,
        is_deleted=model.is_deleted,
        deleted_at=model.deleted_at,
        deleted_by=model.deleted_by,
    )


def to_orm(entity: DocumentEntity) -> DocumentModel:
    """Convert a domain Document entity to a SQLAlchemy ORM instance (INSERT)."""
    return DocumentModel(
        id=entity.id,
        clan_id=entity.clan_id,
        person_id=entity.person_id,
        title=entity.title,
        description=entity.description,
        document_type=entity.document_type,
        storage_path=entity.storage_path,
        file_size_bytes=entity.file_size_bytes,
        mime_type=entity.mime_type,
        original_filename=entity.original_filename,
        taken_date=entity.taken_date,
        taken_place=entity.taken_place,
        is_avatar=entity.is_avatar,
        created_by=entity.created_by,
        is_deleted=entity.is_deleted,
        deleted_at=entity.deleted_at,
        deleted_by=entity.deleted_by,
    )


def apply_to_orm(entity: DocumentEntity, model: DocumentModel) -> None:
    """Apply domain entity state onto an existing ORM model (UPDATE)."""
    for field_name in _MAPPED_FIELDS:
        setattr(model, field_name, getattr(entity, field_name))
