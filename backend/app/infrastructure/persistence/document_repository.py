"""SQLAlchemy implementation of DocumentRepository."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.domain.document.entity import Document as DocumentEntity
from app.infrastructure.persistence.document_mapper import apply_to_orm, to_domain, to_orm
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.models.clan_membership import ClanMembership
from app.models.document import Document as DocumentModel


class SqlAlchemyDocumentRepository:
    """Concrete Document repository backed by SQLAlchemy + PostgreSQL."""

    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow
        self._session = uow.session

    async def get_by_id(self, document_id: uuid.UUID, clan_id: uuid.UUID) -> DocumentEntity | None:
        result = await self._session.execute(
            select(DocumentModel).where(
                DocumentModel.id == document_id,
                DocumentModel.clan_id == clan_id,
                DocumentModel.is_deleted.is_(False),
            )
        )
        model = result.scalar_one_or_none()
        return to_domain(model) if model else None

    async def get_deleted(
        self, document_id: uuid.UUID, clan_id: uuid.UUID
    ) -> DocumentEntity | None:
        """Fetch a soft-deleted document by ID within a clan (for restore)."""
        result = await self._session.execute(
            select(DocumentModel).where(
                DocumentModel.id == document_id,
                DocumentModel.clan_id == clan_id,
                DocumentModel.is_deleted.is_(True),
            )
        )
        model = result.scalar_one_or_none()
        return to_domain(model) if model else None

    async def list_in_clan(
        self,
        clan_id: uuid.UUID,
        *,
        person_id: uuid.UUID | None = None,
        document_type: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[DocumentEntity]:
        from app.core.pagination import paginate_query

        query = select(DocumentModel).where(
            DocumentModel.clan_id == clan_id, DocumentModel.is_deleted.is_(False)
        )
        if person_id:
            query = query.where(DocumentModel.person_id == person_id)
        if document_type:
            query = query.where(DocumentModel.document_type == document_type)

        query = paginate_query(query, DocumentModel, cursor, limit)
        result = await self._session.execute(query)
        return [to_domain(m) for m in result.scalars().all()]

    async def get_person_avatars(
        self,
        clan_id: uuid.UUID,
        person_id: uuid.UUID,
        exclude_id: uuid.UUID,
    ) -> list[DocumentEntity]:
        """Get current avatar documents for a person (excluding a given doc)."""
        result = await self._session.execute(
            select(DocumentModel).where(
                DocumentModel.clan_id == clan_id,
                DocumentModel.person_id == person_id,
                DocumentModel.is_avatar.is_(True),
                DocumentModel.id != exclude_id,
                DocumentModel.is_deleted.is_(False),
            )
        )
        return [to_domain(m) for m in result.scalars().all()]

    async def person_in_clan(self, person_id: uuid.UUID, clan_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(ClanMembership.id).where(
                ClanMembership.person_id == person_id,
                ClanMembership.clan_id == clan_id,
            )
        )
        return result.first() is not None

    async def save(self, doc: DocumentEntity) -> None:
        """Insert or update a Document."""
        self._uow.track(doc)
        existing = await self._session.execute(
            select(DocumentModel).where(DocumentModel.id == doc.id)
        )
        model = existing.scalar_one_or_none()
        if model:
            apply_to_orm(doc, model)
        else:
            self._session.add(to_orm(doc))
