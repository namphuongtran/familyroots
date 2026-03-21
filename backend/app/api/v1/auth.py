"""Auth API routes — thin controller delegating to Auth handlers."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends

from app.application.auth.handlers import (
    AuthCommandHandler,
    AuthQueryHandler,
    FCMTokenHandler,
    SupabaseAuthService,
)
from app.core.security import get_current_user
from app.infrastructure.dependencies import (
    get_auth_command_handler,
    get_auth_query_handler,
    get_fcm_token_handler,
)
from app.schemas.auth import (
    FCMTokenRequest,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    UserUpdateRequest,
)
from app.services.translator import t

router = APIRouter()


@router.post("/register", status_code=201)
async def register(
    body: RegisterRequest, handler: AuthCommandHandler = Depends(get_auth_command_handler)
) -> RegisterResponse:
    """Register a new user — either create a new clan or join an existing one."""
    return await handler.register(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        clan_action=body.clan_action,
        clan_id=body.clan_id,
        clan_name=body.clan_name,
        clan_slug=body.clan_slug,
    )


@router.post("/login")
async def login(
    body: LoginRequest, handler: AuthCommandHandler = Depends(get_auth_command_handler)
) -> LoginResponse:
    """Authenticate a user via Supabase Auth."""
    return await handler.login(email=body.email, password=body.password)


@router.post("/logout")
async def logout(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Invalidate the current session."""
    return {"message": t("auth.logged_out")}


@router.post("/refresh")
async def refresh_token(body: RefreshRequest) -> dict[str, Any]:
    """Exchange a refresh token for a new access token."""
    svc = SupabaseAuthService()
    return await svc.refresh_token(refresh_token=body.refresh_token)


@router.get("/me")
async def get_me(
    current_user: dict[str, Any] = Depends(get_current_user),
    handler: AuthQueryHandler = Depends(get_auth_query_handler),
) -> dict[str, Any]:
    """Return the authenticated user's profile."""
    profile = await handler.get_profile(
        user_id=uuid.UUID(current_user["sub"]),
        email=current_user.get("email", ""),
        full_name=current_user.get("user_metadata", {}).get("full_name", ""),
    )
    return {"data": profile.model_dump()}


@router.patch("/me")
async def update_me(
    body: UserUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Update the authenticated user's profile."""
    svc = SupabaseAuthService()
    await svc.update_profile(
        user_sub=current_user["sub"],
        full_name=body.full_name,
        preferred_locale=body.preferred_locale,
    )
    return {"data": {"message": t("auth.profile_updated")}}


@router.post("/me/fcm-token")
async def register_fcm_token(
    body: FCMTokenRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    handler: FCMTokenHandler = Depends(get_fcm_token_handler),
) -> dict[str, Any]:
    """Register or update an FCM push token."""
    await handler.register_token(
        user_id=current_user["sub"],
        token=body.token,
        device_platform=body.device_platform,
    )
    return {"data": {"message": t("auth.fcm_token_registered")}}


@router.delete("/me/fcm-token")
async def remove_fcm_token(
    body: FCMTokenRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    handler: FCMTokenHandler = Depends(get_fcm_token_handler),
) -> dict[str, Any]:
    """Remove an FCM token (e.g. on logout)."""
    await handler.remove_token(user_id=current_user["sub"], token=body.token)
    return {"data": {"message": t("auth.fcm_token_removed")}}
