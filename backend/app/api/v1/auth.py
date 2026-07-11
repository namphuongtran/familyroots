"""Auth API routes — thin controller delegating to Auth handlers."""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials

from app.application.auth.handlers import (
    AuthCommandHandler,
    AuthQueryHandler,
    AuthSessionService,
    FCMTokenHandler,
)
from app.core.security import get_current_user, security
from app.infrastructure.dependencies import (
    get_auth_command_handler,
    get_auth_query_handler,
    get_auth_session_service,
    get_fcm_token_handler,
)
from app.schemas.auth import (
    AuthenticatedOnboardingRequest,
    FCMTokenRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    UserUpdateRequest,
)
from app.services.translator import t

logger = logging.getLogger(__name__)

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


@router.post("/onboard", status_code=201)
async def onboard_authenticated_user(
    body: AuthenticatedOnboardingRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    handler: AuthCommandHandler = Depends(get_auth_command_handler),
) -> RegisterResponse:
    """Attach the current authenticated user to a clan after OAuth login."""
    return await handler.onboard_authenticated_user(
        user_id=uuid.UUID(current_user["sub"]),
        email=current_user.get("email", ""),
        full_name=current_user.get("user_metadata", {}).get("full_name", ""),
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
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: dict[str, Any] = Depends(get_current_user),
    svc: AuthSessionService = Depends(get_auth_session_service),
) -> dict[str, Any]:
    """Invalidate the current session (revoke refresh tokens)."""
    await svc.logout(access_token=credentials.credentials)
    return {"message": t("auth.logged_out")}


@router.post("/refresh")
async def refresh_token(
    body: RefreshRequest,
    svc: AuthSessionService = Depends(get_auth_session_service),
) -> dict[str, Any]:
    """Exchange a refresh token for a new access token."""
    return await svc.refresh_token(refresh_token=body.refresh_token)


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    svc: AuthSessionService = Depends(get_auth_session_service),
) -> dict[str, Any]:
    """Trigger a password-reset email. ALWAYS returns 200 with the same message,
    regardless of whether the email exists or the provider is reachable — never leak
    account existence or provider state. Reset completion happens client-side via the
    Supabase SDK (verify recovery token + update password)."""
    try:
        await svc.send_password_reset(email=body.email)
    except Exception as e:
        logger.warning("forgot-password: provider call failed (swallowed): %s", e)
    return {"data": {"message": t("auth.password_reset_sent")}}


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
    svc: AuthSessionService = Depends(get_auth_session_service),
) -> dict[str, Any]:
    """Update the authenticated user's profile."""
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
