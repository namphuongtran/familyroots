"""SQLAlchemy implementation of DocumentRepository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.document.entity import Document as DocumentEntity
from app.domain.document.repository import DocumentRepository
from app.infrastructure.persistence.document_mapper import apply_to_orm, to_domain, to_orm
from app.models.document import Document as DocumentModel


class SqlAlchemyDocumentRepository:
    """Concrete Document repository backed by SQLAlchemy + PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self, document_id: uuid.UUID, clan_id: uuid.UUID
    ) -> DocumentEntity | None:
        result = await self._session.execute(
            select(DocumentModel).where(
                DocumentModel.id == document_id, DocumentModel.clan_id == clan_id
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

        query = select(DocumentModel).where(DocumentModel.clan_id == clan_id)
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
            )
        )
        return [to_domain(m) for m in result.scalars().all()]

    async def save(self, doc: DocumentEntity) -> None:
        """Insert or update a Document."""
        existing = await self._session.execute(
            select(DocumentModel).where(DocumentModel.id == doc.id)
        )
        model = existing.scalar_one_or_none()
        if model:
            apply_to_orm(doc, model)
        else:
            self._session.add(to_orm(doc))

    async def delete(self, doc: DocumentEntity) -> None:
        """Hard-delete a document."""
        result = await self._session.execute(
            select(DocumentModel).where(DocumentModel.id == doc.id)
        )
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
