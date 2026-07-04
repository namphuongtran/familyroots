"""Claim application handlers.

These handlers orchestrate the process of a user claiming an identity in the family tree,
as well as admins reviewing (approving/rejecting) those claims.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.domain.person.claim_entity import IdentityClaim as ClaimEntity
from app.domain.person.claim_repository import ClaimQueryPort, ClaimRepository
from app.models.audit_log import AuditLog
from app.models.identity_claim import IdentityClaim as ClaimModel
from app.models.user_clan_role import UserClanRole
from app.schemas.claim import IdentityClaimPaginatedResponse, IdentityClaimResponse


class ClaimCommandHandler:
    def __init__(self, repo: ClaimRepository, uow: Any) -> None:
        self._repo = repo
        self._uow = uow

    async def submit_claim(
        self, *, user_id: uuid.UUID, person_id: uuid.UUID, requester_note: str | None
    ) -> IdentityClaimResponse:
        """Submit a new identity claim for a global person."""
        # Val 1: Does user already have a linked person?
        user = await self._repo.get_user_profile(user_id)
        if not user:
            raise NotFoundError("user_not_found")
        if user.person_id:
            raise ConflictError("user_already_linked_to_person")

        # Val 2: Is person already linked to another user?
        if await self._repo.is_person_linked(person_id):
            raise ConflictError("person_already_linked_to_user")

        # Val 3: Does user already have ANY pending claims globally?
        if await self._repo.has_pending_claims(user_id):
            raise ConflictError("user_already_has_pending_claim")

        # Val 4: Person must exist
        person = await self._repo.get_person(person_id)
        if not person:
            raise NotFoundError("person_not_found")

        # Create
        claim_model = ClaimModel(
            user_id=user_id, person_id=person_id, requester_note=requester_note, status="PENDING"
        )
        self._repo.add_claim(claim_model)
        # NOTE: do not uow.track(claim_model) — IdentityClaim is a plain ORM model,
        # not an AggregateRoot, so it has no collect_events() and would crash at
        # commit. This context records audit rows manually via add_audit (as the
        # sibling cancel/approve/reject/unlink methods do).
        await self._uow.flush()

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
        self._repo.add_audit(audit)

        await self._uow.commit()

        return IdentityClaimResponse.model_validate(claim_model)

    async def cancel_claim(self, *, claim_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Cancel a pending claim submitted by the user."""
        claim = await self._repo.get_claim(claim_id)
        if not claim:
            raise NotFoundError("claim_not_found")

        # Domain entity logic
        entity = ClaimEntity(
            id=claim.id,
            user_id=claim.user_id,
            person_id=claim.person_id,
            status=claim.status,
        )
        entity.cancel(user_id)  # ForbiddenError if not owner, ConflictError if not PENDING

        claim.status = entity.status

        # Get the clan_id for the audit log
        person = await self._repo.get_person(claim.person_id)
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
            self._repo.add_audit(audit)

        await self._uow.commit()

    async def approve_claim(
        self, *, claim_id: uuid.UUID, admin_id: uuid.UUID, reviewer_note: str | None
    ) -> IdentityClaimResponse:
        """Approve a claim by a clan admin of the person's origin clan."""
        claim = await self._repo.get_claim(claim_id, load_person=True)
        if not claim or not claim.person:
            raise NotFoundError("claim_not_found")

        # Auth check: admin_id must be "admin" in person.created_by_clan_id
        await self._verify_admin_access(admin_id, claim.person.created_by_clan_id)

        # Race Guard 1: User Profile still not linked
        user = await self._repo.get_user_profile(claim.user_id)
        if not user or user.person_id:
            raise ConflictError("user_already_linked")

        # Race Guard 2: Person still not linked
        if await self._repo.is_person_linked(claim.person_id):
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
        claim.reviewed_at = datetime.now(UTC)

        user.person_id = claim.person_id

        # Auto-reject other pending claims for this person
        await self._repo.auto_reject_other_pending_claims(
            person_id=claim.person_id,
            exclude_claim_id=claim.id,
            admin_id=admin_id,
            reviewer_note="Person verified by another user.",
        )

        # Auto-grant default `viewer` role in the person's created_by_clan if user has no role
        existing_role = await self._repo.get_role(claim.user_id, claim.person.created_by_clan_id)
        if not existing_role:
            self._repo.add_role(
                UserClanRole(
                    user_id=claim.user_id,
                    clan_id=claim.person.created_by_clan_id,
                    role="viewer",
                    is_approved=True,
                    approved_by=admin_id,
                    approved_at=datetime.now(UTC),
                )
            )

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
        self._repo.add_audit(audit)

        await self._uow.commit()
        return IdentityClaimResponse.model_validate(claim)

    async def reject_claim(
        self, *, claim_id: uuid.UUID, admin_id: uuid.UUID, reviewer_note: str | None
    ) -> IdentityClaimResponse:
        """Reject a claim by a clan admin."""
        claim = await self._repo.get_claim(claim_id, load_person=True)
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
        claim.reviewed_at = datetime.now(UTC)

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
        self._repo.add_audit(audit)

        await self._uow.commit()
        return IdentityClaimResponse.model_validate(claim)

    async def unlink_identity(
        self, *, clan_id: uuid.UUID, user_id_to_unlink: uuid.UUID, admin_id: uuid.UUID, reason: str
    ) -> None:
        """Unlink a user's identity and cancel/reject the original claim."""
        # 1. Authorize clan admin
        await self._verify_admin_access(admin_id, clan_id)

        # 2. Verify target user
        user = await self._repo.get_user_profile(user_id_to_unlink)
        if not user or not user.person_id:
            raise NotFoundError("user_not_linked_to_person")

        # 3. Ensure the person belongs to the clan the admin controls
        person = await self._repo.get_person(user.person_id)
        if not person or person.created_by_clan_id != clan_id:
            raise ForbiddenError("person_not_controlled_by_this_clan")

        person_id = user.person_id

        # 4. Unlink
        user.person_id = None

        # 5. Cancel or reject their last approved claim
        claim = await self._repo.get_last_approved_claim(user_id_to_unlink, person_id)
        if claim:
            claim.status = "CANCELLED"
            claim.reviewer_note = f"Unlinked by Admin: {reason}"
            claim.reviewed_by = admin_id
            claim.reviewed_at = datetime.now(UTC)

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
        self._repo.add_audit(audit)

        # 6. Auto-reject orphans (PENDING claims for this user or this person)
        await self._repo.auto_reject_all_pending_claims(
            user_id=user_id_to_unlink,
            person_id=person_id,
            admin_id=admin_id,
            reviewer_note=f"Auto-rejected during identity unlink: {reason}",
        )

        await self._uow.commit()

    async def prelink_identity(
        self,
        *,
        clan_id: uuid.UUID,
        user_id_to_link: uuid.UUID,
        person_id: uuid.UUID,
        admin_id: uuid.UUID,
    ) -> IdentityClaimResponse:
        """Admins directly link a clan member to a person record, bypassing the claim workflow."""
        await self._verify_admin_access(admin_id, clan_id)

        user = await self._repo.get_user_profile(user_id_to_link)
        if not user:
            raise NotFoundError("user_not_found")
        if user.person_id:
            raise ConflictError("user_already_linked_to_person")

        person = await self._repo.get_person(person_id)
        if not person:
            raise NotFoundError("person_not_found")
        if person.created_by_clan_id != clan_id:
            raise ForbiddenError("person_not_controlled_by_this_clan")

        if await self._repo.is_person_linked(person_id):
            raise ConflictError("person_already_linked")

        # Ensure user is actually in the clan
        role = await self._repo.get_role(user_id_to_link, clan_id)
        if not role:
            raise ForbiddenError("user_not_in_clan")

        user.person_id = person_id

        # Auto-reject orphans
        await self._repo.auto_reject_all_pending_claims(
            user_id=user_id_to_link,
            person_id=person_id,
            admin_id=admin_id,
            reviewer_note="Auto-rejected during Admin Pre-link.",
        )

        # Create audit record
        claim_model = ClaimModel(
            user_id=user_id_to_link,
            person_id=person_id,
            status="APPROVED",
            requester_note="Admin Pre-link",
            reviewer_note="Admin Pre-link",
            reviewed_by=admin_id,
            reviewed_at=datetime.now(UTC),
        )
        self._repo.add_claim(claim_model)
        # See submit_claim: IdentityClaim is an ORM model, not an AggregateRoot;
        # audit is recorded manually below, so it must not be tracked on the UoW.
        await self._uow.flush()

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
        self._repo.add_audit(audit)

        await self._uow.commit()
        return IdentityClaimResponse.model_validate(claim_model)

    async def _verify_admin_access(self, admin_id: uuid.UUID, clan_id: uuid.UUID | None) -> None:
        if not clan_id:
            raise ForbiddenError("person_has_no_controlling_clan")

        role = await self._repo.get_role(admin_id, clan_id)
        if role != "admin":
            raise ForbiddenError("only_clan_admin_can_review_claims")


class ClaimQueryHandler:
    def __init__(self, query_port: ClaimQueryPort) -> None:
        self._query_port = query_port

    async def list_clan_claims(
        self, *, clan_id: uuid.UUID, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> IdentityClaimPaginatedResponse:
        """List claims linked to persons created by the given clan."""
        claims, total = await self._query_port.list_clan_claims(clan_id, status, page, page_size)

        return IdentityClaimPaginatedResponse(
            items=[IdentityClaimResponse.model_validate(c) for c in claims],
            total=total,
            page=page,
            page_size=page_size,
        )
