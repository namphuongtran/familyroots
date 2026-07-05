"""Mapper between the Invitation domain entity and its SQLAlchemy ORM model.

Keeps the domain layer free of SQLAlchemy by providing explicit conversions. The
write side transitions status via the repository's atomic ``transition_status`` CAS,
so there is no generic ``apply_to_orm`` here — only load (``to_domain``).
"""

from __future__ import annotations

from app.domain.invitation.entity import Invitation as InvitationEntity
from app.models.clan_invitation import ClanInvitation as InvitationModel


def to_domain(model: InvitationModel) -> InvitationEntity:
    """Convert a SQLAlchemy ClanInvitation ORM instance to a domain entity."""
    return InvitationEntity(
        id=model.id,
        clan_id=model.clan_id,
        email=model.email,
        role=model.role,
        token=model.token,
        status=model.status,
        invited_by=model.invited_by,
        expires_at=model.expires_at,
        accepted_by=model.accepted_by,
        accepted_at=model.accepted_at,
    )
