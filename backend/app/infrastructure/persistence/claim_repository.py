"""SQLAlchemy implementations for Identity Claims bounded context."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.person.claim_repository import ClaimQueryPort, ClaimRepository
from app.models.identity_claim import IdentityClaim as ClaimModel
from app.models.person import Person
from app.models.user_clan_role import UserClanRole
from app.models.user_profile import UserProfile


class SqlAlchemyClaimRepository(ClaimRepository):
    """SQLAlchemy implementation of Identity Claims write persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_profile(self, user_id: uuid.UUID) -> UserProfile | None:
        return await self._session.get(UserProfile, user_id)

    async def get_person(self, person_id: uuid.UUID) -> Person | None:
        return await self._session.get(Person, person_id)

    async def get_claim(self, claim_id: uuid.UUID, load_person: bool = False) -> ClaimModel | None:
        options = [selectinload(ClaimModel.person)] if load_person else []
        return await self._session.get(ClaimModel, claim_id, options=options)

    async def is_person_linked(self, person_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(UserProfile.id).where(UserProfile.person_id == person_id).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def has_pending_claims(self, user_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(ClaimModel.id).where(ClaimModel.user_id == user_id, ClaimModel.status == "PENDING").limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_role(self, user_id: uuid.UUID, clan_id: uuid.UUID) -> str | None:
        result = await self._session.execute(
            select(UserClanRole.role).where(
                UserClanRole.user_id == user_id,
                UserClanRole.clan_id == clan_id,
                UserClanRole.is_approved.is_(True)
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_last_approved_claim(self, user_id: uuid.UUID, person_id: uuid.UUID) -> ClaimModel | None:
        result = await self._session.execute(
            select(ClaimModel).where(
                ClaimModel.user_id == user_id,
                ClaimModel.person_id == person_id,
                ClaimModel.status == "APPROVED"
            ).order_by(ClaimModel.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    def add_claim(self, claim: ClaimModel) -> None:
        self._session.add(claim)

    def add_audit(self, audit: Any) -> None:
        self._session.add(audit)

    def add_role(self, role: UserClanRole) -> None:
        self._session.add(role)

    async def auto_reject_other_pending_claims(
        self,
        person_id: uuid.UUID,
        exclude_claim_id: uuid.UUID,
        admin_id: uuid.UUID,
        reviewer_note: str,
    ) -> None:
        await self._session.execute(
            update(ClaimModel)
            .where(ClaimModel.person_id == person_id, ClaimModel.id != exclude_claim_id, ClaimModel.status == "PENDING")
            .values(
                status="REJECTED",
                reviewer_note=reviewer_note,
                reviewed_by=admin_id,
                reviewed_at=datetime.now(UTC)
            )
        )

    async def auto_reject_all_pending_claims(
        self,
        user_id: uuid.UUID,
        person_id: uuid.UUID,
        admin_id: uuid.UUID,
        reviewer_note: str,
    ) -> None:
        await self._session.execute(
            update(ClaimModel)
            .where(
                or_(
                    ClaimModel.user_id == user_id,
                    ClaimModel.person_id == person_id
                ),
                ClaimModel.status == "PENDING"
            )
            .values(
                status="REJECTED",
                reviewer_note=reviewer_note,
                reviewed_by=admin_id,
                reviewed_at=datetime.now(UTC)
            )
        )


class SqlAlchemyClaimQueryPort(ClaimQueryPort):
    """SQLAlchemy implementation of Identity Claims read persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_clan_claims(
        self,
        clan_id: uuid.UUID,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ClaimModel], int]:
        query = (
            select(ClaimModel)
            .join(Person, ClaimModel.person_id == Person.id)
            .where(Person.created_by_clan_id == clan_id)
        )

        if status:
            query = query.where(ClaimModel.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total = await self._session.scalar(count_query) or 0

        query = query.order_by(ClaimModel.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self._session.execute(query)
        claims = list(result.scalars().all())

        return claims, total
