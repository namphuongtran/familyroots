"""Pydantic DTOs for the invitation API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class InvitationCreateRequest(BaseModel):
    email: EmailStr
    role: str = "viewer"

    @field_validator("role")
    @classmethod
    def _role_allowed(cls, v: str) -> str:
        if v not in ("admin", "editor", "viewer"):
            raise ValueError("role must be one of: admin, editor, viewer")
        return v


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    clan_id: uuid.UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime


class InvitationCreatedResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    token: str
    expires_at: datetime
    accept_path: str  # e.g. "/api/v1/invitations/{token}/accept" — admin shares this


class InvitationAcceptedResponse(BaseModel):
    clan_id: uuid.UUID
    role: str
    message: str
