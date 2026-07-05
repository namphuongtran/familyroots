import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.shared.exceptions import ConflictError, ForbiddenError


@dataclass
class IdentityClaim:
    user_id: uuid.UUID
    person_id: uuid.UUID
    requester_note: str | None = None
    status: str = "PENDING"
    reviewer_note: str | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)

    def cancel(self, user_id: uuid.UUID) -> None:
        # Domain exceptions (not ValueError) so the API maps these to 403/409 via
        # the DomainError handler — a bare ValueError falls through to a 500.
        if self.user_id != user_id:
            raise ForbiddenError("claim.not_owned")
        if self.status != "PENDING":
            raise ConflictError("claim.not_pending")

        self.status = "CANCELLED"

    def approve(self, admin_id: uuid.UUID, reviewer_note: str | None = None) -> None:
        if self.status != "PENDING":
            raise ConflictError("claim.not_pending")

        self.status = "APPROVED"
        self.reviewed_by = admin_id
        self.reviewer_note = reviewer_note
        self.reviewed_at = datetime.now(UTC)

    def reject(self, admin_id: uuid.UUID, reviewer_note: str | None = None) -> None:
        if self.status != "PENDING":
            raise ConflictError("claim.not_pending")

        self.status = "REJECTED"
        self.reviewed_by = admin_id
        self.reviewer_note = reviewer_note
        self.reviewed_at = datetime.now(UTC)
