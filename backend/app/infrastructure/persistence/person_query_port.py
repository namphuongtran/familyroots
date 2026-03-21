"""SQLAlchemy implementation of the Person read operations."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.person.query_port import PersonQueryPort
from app.models.document import Document
from app.models.event import Event
from app.models.marriage import Marriage
from app.models.parent_child import ParentChild
from app.schemas.document import DocumentSummary
from app.schemas.event import EventResponse
from app.schemas.marriage import MarriageResponse
from app.schemas.parent_child import ParentChildResponse


class SqlAlchemyPersonQueryPort(PersonQueryPort):
    """SQLAlchemy implementation of PersonQueryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_marriages(self, person_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(Marriage).where(
                or_(Marriage.person1_id == person_id, Marriage.person2_id == person_id),
                Marriage.is_deleted.is_(False),
            )
        )
        marriages = result.scalars().all()
        return [MarriageResponse.model_validate(m).model_dump() for m in marriages]

    async def get_parent_child_links(self, person_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(ParentChild).where(
                or_(ParentChild.parent_id == person_id, ParentChild.child_id == person_id),
                ParentChild.is_deleted.is_(False),
            )
        )
        links = result.scalars().all()
        return [ParentChildResponse.model_validate(link).model_dump() for link in links]

    async def get_documents(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(Document).where(Document.clan_id == clan_id, Document.person_id == person_id)
        )
        docs = result.scalars().all()
        return [DocumentSummary.model_validate(d).model_dump() for d in docs]

    async def get_events(self, clan_id: uuid.UUID, person_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(Event).where(Event.clan_id == clan_id, Event.person_id == person_id)
        )
        events = result.scalars().all()
        return [EventResponse.model_validate(e).model_dump() for e in events]
