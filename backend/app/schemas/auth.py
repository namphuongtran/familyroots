"""Pydantic v2 schemas for Auth requests and responses."""

import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1, max_length=255)
    clan_action: Literal["join", "create"]
    clan_id: uuid.UUID | None = None
    clan_name: str | None = Field(None, max_length=255)
    clan_slug: str | None = Field(None, max_length=100)


class AuthenticatedOnboardingRequest(BaseModel):
    clan_action: Literal["join", "create"]
    clan_id: uuid.UUID | None = None
    clan_name: str | None = Field(None, max_length=255)
    clan_slug: str | None = Field(None, max_length=100)


class RegisterResponse(BaseModel):
    """Onboard-only now (ADR-021): POST /auth/register is non-enumerating and
    returns a uniform ``{"message": ...}`` body built by the route, not this
    schema. POST /auth/onboard (already-authenticated users attaching to a
    clan) still returns this full shape via ``_assign_clan_membership``."""

    user_id: uuid.UUID
    email: str
    full_name: str
    clan_id: uuid.UUID
    is_approved: bool
    message: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserProfile(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    clan_id: uuid.UUID | None = None
    clan_name: str | None = None
    role: str | None = None
    is_approved: bool = False
    has_pending_membership: bool = False
    person_id: uuid.UUID | None = None
    preferred_locale: str = "vi"


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserProfile


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    preferred_locale: str | None = Field(None, pattern="^(vi|en|zh|fr)$")


class FCMTokenRequest(BaseModel):
    token: str = Field(..., max_length=500)
    device_platform: Literal["android", "ios", "web"]


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResendVerificationRequest(BaseModel):
    email: EmailStr
