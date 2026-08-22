"""Read models for the invitation query side.

Separate from the ORM row on purpose. ``status`` here is **derived**, not the stored
column, so handing the route an ORM row would hand it the field that lies (S-019).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class InvitationListItem:
    """One row of ``GET /clans/{clan_id}/invitations``.

    ``status`` is produced by ``app.domain.invitation.entity.effective_status`` from the
    stored status and ``expires_at``. Every other field is the stored value. The contract
    (``docs/contracts/rest-invitations-api.md``) says which is which.
    """

    id: uuid.UUID
    clan_id: uuid.UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime
