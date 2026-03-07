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


class RegisterResponse(BaseModel):
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
    member_id: uuid.UUID | None = None
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
