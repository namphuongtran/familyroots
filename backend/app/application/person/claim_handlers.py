"""Claim application handlers.

These handlers orchestrate the process of a user claiming an identity in the family tree,
as well as admins reviewing (approving/rejecting) those claims.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.domain.person.claim_entity import IdentityClaim as ClaimEntity
from app.models.clan_membership import ClanMembership
from app.models.identity_claim import IdentityClaim as ClaimModel
from app.models.person import Person
from app.models.user_profile import UserProfile
from app.models.user_clan_role import UserClanRole
from app.models.audit_log import AuditLog
from app.schemas.claim import IdentityClaimResponse, IdentityClaimPaginatedResponse


class ClaimCommandHandler:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def submit_claim(self, *, user_id: uuid.UUID, person_id: uuid.UUID, requester_note: str | None) -> IdentityClaimResponse:
        """Submit a new identity claim for a global person."""
        # Val 1: Does user already have a linked person?
        user = await self._db.get(UserProfile, user_id)
        if not user:
            raise NotFoundError("user_not_found")
        if user.person_id:
            raise ConflictError("user_already_linked_to_person")

        # Val 2: Is person already linked to another user?
        existing_link = await self._db.execute(
            select(UserProfile.id).where(UserProfile.person_id == person_id).limit(1)
        )
        if existing_link.scalar_one_or_none():
            raise ConflictError("person_already_linked_to_user")

        # Val 3: Does user already have ANY pending claims globally?
        pending_claims = await self._db.execute(
            select(ClaimModel.id).where(ClaimModel.user_id == user_id, ClaimModel.status == "PENDING").limit(1)
        )
        if pending_claims.scalar_one_or_none():
            raise ConflictError("user_already_has_pending_claim")

        # Val 4: Person must exist
        person = await self._db.get(Person, person_id)
        if not person:
            raise NotFoundError("person_not_found")

        # Create
        claim_model = ClaimModel(
            user_id=user_id,
            person_id=person_id,
            requester_note=requester_note,
            status="PENDING"
        )
        self._db.add(claim_model)
        await self._db.flush()

        audit = AuditLog(
            clan_id=person.created_by_clan_id,
            actor_id=user_id,
            actor_role="viewer",  # They are applying, so minimum role
            action="claim.submit",
            resource_type="identity_claim",
            resource_id=claim_model.id,
            old_value=None,
            new_value={"status": "PENDING", "person_id": str(person_id)},
        )
        self._db.add(audit)

        await self._db.commit()
        await self._db.refresh(claim_model)

        return IdentityClaimResponse.model_validate(claim_model)

    async def cancel_claim(self, *, claim_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Cancel a pending claim submitted by the user."""
        claim = await self._db.get(ClaimModel, claim_id)
        if not claim:
            raise NotFoundError("claim_not_found")
        
        # Domain entity logic
        entity = ClaimEntity(
            id=claim.id,
            user_id=claim.user_id,
            person_id=claim.person_id,
            status=claim.status,
        )
        entity.cancel(user_id) # Raises ValueError if not owner or not PENDING

        claim.status = entity.status

        # Get the clan_id for the audit log
        person = await self._db.get(Person, claim.person_id)
        if person:
            audit = AuditLog(
                clan_id=person.created_by_clan_id,
                actor_id=user_id,
                actor_role="viewer",
                action="claim.cancel",
                resource_type="identity_claim",
                resource_id=claim.id,
                old_value={"status": "PENDING"},
                new_value={"status": "CANCELLED"},
            )
            self._db.add(audit)

        await self._db.commit()

    async def approve_claim(self, *, claim_id: uuid.UUID, admin_id: uuid.UUID, reviewer_note: str | None) -> IdentityClaimResponse:
        """Approve a claim by a clan admin of the person's origin clan."""
        claim = await self._db.get(ClaimModel, claim_id, options=[selectinload(ClaimModel.person)])
        if not claim or not claim.person:
            raise NotFoundError("claim_not_found")

        # Auth check: admin_id must be "admin" in person.created_by_clan_id
        await self._verify_admin_access(admin_id, claim.person.created_by_clan_id)

        # Race Guard 1: User Profile still not linked
        user = await self._db.get(UserProfile, claim.user_id)
        if not user or user.person_id:
            raise ConflictError("user_already_linked")
        
        # Race Guard 2: Person still not linked
        existing_link = await self._db.execute(
            select(UserProfile.id).where(UserProfile.person_id == claim.person_id).limit(1)
        )
        if existing_link.scalar_one_or_none():
            raise ConflictError("person_already_linked")

        # Domain Logic
        entity = ClaimEntity(
            id=claim.id,
            user_id=claim.user_id,
            person_id=claim.person_id,
            status=claim.status,
        )
        entity.approve(admin_id, reviewer_note)

        # Apply state
        claim.status = entity.status
        claim.reviewed_by = entity.reviewed_by
        claim.reviewer_note = entity.reviewer_note
        claim.reviewed_at = datetime.now(timezone.utc)

        user.person_id = claim.person_id

        # Auto-reject other pending claims for this person
        await self._db.execute(
            update(ClaimModel)
            .where(ClaimModel.person_id == claim.person_id, ClaimModel.id != claim.id, ClaimModel.status == "PENDING")
            .values(
                status="REJECTED",
                reviewer_note="Person verified by another user.",
                reviewed_by=admin_id,
                reviewed_at=datetime.now(timezone.utc)
            )
        )
        
        # Auto-grant default `viewer` role in the person's created_by_clan if user has no role
        existing_role = await self._db.execute(
            select(UserClanRole.id).where(
                UserClanRole.user_id == claim.user_id,
                UserClanRole.clan_id == claim.person.created_by_clan_id
            ).limit(1)
        )
        if not existing_role.scalar_one_or_none():
            self._db.add(UserClanRole(
                user_id=claim.user_id,
                clan_id=claim.person.created_by_clan_id,
                role="viewer",
                is_approved=True
            ))

        audit = AuditLog(
            clan_id=claim.person.created_by_clan_id,
            actor_id=admin_id,
            actor_role="admin",
            action="claim.approve",
            resource_type="identity_claim",
            resource_id=claim.id,
            old_value={"status": "PENDING"},
            new_value={"status": "APPROVED", "person_id": str(claim.person_id)},
        )
        self._db.add(audit)

        await self._db.commit()
        await self._db.refresh(claim)
        return IdentityClaimResponse.model_validate(claim)

    async def reject_claim(self, *, claim_id: uuid.UUID, admin_id: uuid.UUID, reviewer_note: str | None) -> IdentityClaimResponse:
        """Reject a claim by a clan admin."""
        claim = await self._db.get(ClaimModel, claim_id, options=[selectinload(ClaimModel.person)])
        if not claim or not claim.person:
            raise NotFoundError("claim_not_found")

        # Auth check
        await self._verify_admin_access(admin_id, claim.person.created_by_clan_id)

        entity = ClaimEntity(
            id=claim.id,
            user_id=claim.user_id,
            person_id=claim.person_id,
            status=claim.status,
        )
        entity.reject(admin_id, reviewer_note)

        claim.status = entity.status
        claim.reviewed_by = entity.reviewed_by
        claim.reviewer_note = entity.reviewer_note
        claim.reviewed_at = datetime.now(timezone.utc)

        audit = AuditLog(
            clan_id=claim.person.created_by_clan_id,
            actor_id=admin_id,
            actor_role="admin",
            action="claim.reject",
            resource_type="identity_claim",
            resource_id=claim.id,
            old_value={"status": "PENDING"},
            new_value={"status": "REJECTED"},
        )
        self._db.add(audit)

        await self._db.commit()
        await self._db.refresh(claim)
        return IdentityClaimResponse.model_validate(claim)

    async def unlink_identity(self, *, clan_id: uuid.UUID, user_id_to_unlink: uuid.UUID, admin_id: uuid.UUID, reason: str) -> None:
        """Unlink a user's identity and cancel/reject the original claim, and auto-reject their orphans."""
        # 1. Authorize clan admin
        await self._verify_admin_access(admin_id, clan_id)

        # 2. Verify target user
        user = await self._db.get(UserProfile, user_id_to_unlink)
        if not user or not user.person_id:
            raise NotFoundError("user_not_linked_to_person")

        # 3. Ensure the person belongs to the clan the admin controls
        person = await self._db.get(Person, user.person_id)
        if not person or person.created_by_clan_id != clan_id:
            raise ForbiddenError("person_not_controlled_by_this_clan")

        person_id = user.person_id

        # 4. Unlink
        user.person_id = None

        # 5. Cancel or reject their last approved claim
        last_approved_claim = await self._db.execute(
            select(ClaimModel).where(
                ClaimModel.user_id == user_id_to_unlink,
                ClaimModel.person_id == person_id,
                ClaimModel.status == "APPROVED"
            ).order_by(ClaimModel.created_at.desc()).limit(1)
        )
        claim = last_approved_claim.scalar_one_or_none()
        if claim:
            claim.status = "CANCELLED"
            claim.reviewer_note = f"Unlinked by Admin: {reason}"
            claim.reviewed_by = admin_id
            claim.reviewed_at = datetime.now(timezone.utc)

        audit = AuditLog(
            clan_id=clan_id,
            actor_id=admin_id,
            actor_role="admin",
            action="claim.unlink",
            resource_type="identity_claim",
            resource_id=claim.id if claim else None,
            old_value={"person_id": str(person_id)},
            new_value={"person_id": None, "reason": reason},
        )
        self._db.add(audit)

        # 6. Auto-reject orphans (PENDING claims for this user or this person)
        from sqlalchemy import or_
        await self._db.execute(
            update(ClaimModel)
            .where(
                or_(
                    ClaimModel.user_id == user_id_to_unlink,
                    ClaimModel.person_id == person_id
                ),
                ClaimModel.status == "PENDING"
            )
            .values(
                status="REJECTED",
                reviewer_note=f"Auto-rejected during identity unlink: {reason}",
                reviewed_by=admin_id,
                reviewed_at=datetime.now(timezone.utc)
            )
        )

        await self._db.commit()

    async def prelink_identity(self, *, clan_id: uuid.UUID, user_id_to_link: uuid.UUID, person_id: uuid.UUID, admin_id: uuid.UUID) -> IdentityClaimResponse:
        """Admins directly link a clan member to a person record, bypassing the claim workflow."""
        await self._verify_admin_access(admin_id, clan_id)

        user = await self._db.get(UserProfile, user_id_to_link)
        if not user:
            raise NotFoundError("user_not_found")
        if user.person_id:
            raise ConflictError("user_already_linked_to_person")

        person = await self._db.get(Person, person_id)
        if not person:
            raise NotFoundError("person_not_found")
        if person.created_by_clan_id != clan_id:
            raise ForbiddenError("person_not_controlled_by_this_clan")

        existing_link = await self._db.execute(select(UserProfile.id).where(UserProfile.person_id == person_id).limit(1))
        if existing_link.scalar_one_or_none():
            raise ConflictError("person_already_linked")

        # Ensure user is actually in the clan
        role_check = await self._db.execute(
            select(UserClanRole.id).where(
                UserClanRole.user_id == user_id_to_link,
                UserClanRole.clan_id == clan_id,
                UserClanRole.is_approved.is_(True)
            ).limit(1)
        )
        if not role_check.scalar_one_or_none():
            raise ForbiddenError("user_not_in_clan")

        user.person_id = person_id

        # Auto-reject orphans
        from sqlalchemy import or_
        await self._db.execute(
            update(ClaimModel)
            .where(
                or_(
                    ClaimModel.user_id == user_id_to_link,
                    ClaimModel.person_id == person_id
                ),
                ClaimModel.status == "PENDING"
            )
            .values(
                status="REJECTED",
                reviewer_note="Auto-rejected during Admin Pre-link.",
                reviewed_by=admin_id,
                reviewed_at=datetime.now(timezone.utc)
            )
        )

        # Create audit record
        claim_model = ClaimModel(
            user_id=user_id_to_link,
            person_id=person_id,
            status="APPROVED",
            requester_note="Admin Pre-link",
            reviewer_note="Admin Pre-link",
            reviewed_by=admin_id,
            reviewed_at=datetime.now(timezone.utc)
        )
        self._db.add(claim_model)
        await self._db.flush()

        audit = AuditLog(
            clan_id=clan_id,
            actor_id=admin_id,
            actor_role="admin",
            action="claim.prelink",
            resource_type="identity_claim",
            resource_id=claim_model.id,
            old_value=None,
            new_value={"person_id": str(person_id), "user_id": str(user_id_to_link)},
        )
        self._db.add(audit)
        
        await self._db.commit()
        await self._db.refresh(claim_model)
        return IdentityClaimResponse.model_validate(claim_model)

    async def _verify_admin_access(self, admin_id: uuid.UUID, clan_id: uuid.UUID | None) -> None:
        if not clan_id:
            raise ForbiddenError("person_has_no_controlling_clan")
            
        role = await self._db.execute(
            select(UserClanRole.role).where(
                UserClanRole.user_id == admin_id,
                UserClanRole.clan_id == clan_id,
                UserClanRole.is_approved.is_(True)
            ).limit(1)
        )
        if role.scalar_one_or_none() != "admin":
            raise ForbiddenError("only_clan_admin_can_review_claims")


class ClaimQueryHandler:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_clan_claims(self, *, clan_id: uuid.UUID, status: str | None = None, page: int = 1, page_size: int = 20) -> IdentityClaimPaginatedResponse:
        """List claims linked to persons created by the given clan."""
        query = (
            select(ClaimModel)
            .join(Person, ClaimModel.person_id == Person.id)
            .where(Person.created_by_clan_id == clan_id)
        )
        
        if status:
            query = query.where(ClaimModel.status == status)

        # Pagination
        count_query = select(func.count()).select_from(query.subquery())
        total = await self._db.scalar(count_query) or 0

        query = query.order_by(ClaimModel.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self._db.execute(query)
        claims = result.scalars().all()

        return IdentityClaimPaginatedResponse(
            items=[IdentityClaimResponse.model_validate(c) for c in claims],
            total=total,
            page=page,
            page_size=page_size
        )
