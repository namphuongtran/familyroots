"""FCM push notification sender service."""

import asyncio as asyncio
import logging
import uuid
from typing import Any

import firebase_admin
from firebase_admin import credentials
from firebase_admin import messaging as messaging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.translator import t

logger = logging.getLogger(__name__)

_firebase_app: firebase_admin.App | None = None

# FCM's documented maximum messages per send_each call.
_FCM_BATCH_LIMIT = 500


def init_firebase() -> None:
    """Initialize the Firebase Admin SDK once at application startup."""
    global _firebase_app
    if not _firebase_app:
        try:
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            _firebase_app = firebase_admin.initialize_app(cred)
        except (FileNotFoundError, ValueError) as e:
            logger.warning("Firebase init skipped: %s", e)


async def _remove_invalid_token(fcm_token: str, db: AsyncSession | None = None) -> None:
    """Stage removal of an unregistered FCM token. Does NOT commit — the caller's
    transaction (the scheduler's per-event commit) persists it, so this never commits
    a shared broadcast session mid-flight."""
    if db is None:
        return
    await db.execute(
        text("DELETE FROM public.user_fcm_tokens WHERE token = :token"),
        {"token": fcm_token},
    )


def _build_message(
    fcm_token: str,
    title_key: str,
    body_key: str,
    locale: str,
    data: dict[str, Any] | None,
    **kwargs: Any,
) -> messaging.Message:
    """One localized FCM Message (shared by single sends and clan batches)."""
    return messaging.Message(
        notification=messaging.Notification(
            title=t(title_key, locale=locale, **kwargs),
            body=t(body_key, locale=locale, **kwargs),
        ),
        data={k: str(v) for k, v in (data or {}).items()},
        token=fcm_token,
        android=messaging.AndroidConfig(priority="normal"),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default"),
            ),
        ),
    )


async def send_push_notification(
    fcm_token: str,
    title_key: str,
    body_key: str,
    locale: str = "vi",
    data: dict[str, Any] | None = None,
    db: AsyncSession | None = None,
    **kwargs: Any,
) -> bool:
    """Send a single FCM push notification.

    Returns True on success, False on failure. Never raises — notification
    failure must not break the calling flow.
    """
    try:
        message = _build_message(fcm_token, title_key, body_key, locale, data, **kwargs)
        await asyncio.to_thread(messaging.send, message)
        return True

    except messaging.UnregisteredError:
        await _remove_invalid_token(fcm_token, db)
        return False

    except Exception as e:
        logger.error("FCM send failed: %s (token=%s)", e, fcm_token[:20])
        return False


async def send_to_clan(
    clan_id: uuid.UUID,
    title_key: str,
    body_key: str,
    db: AsyncSession,
    exclude_user_id: uuid.UUID | None = None,
    **kwargs: Any,
) -> tuple[int, int]:
    """Broadcast to all approved clan members in each member's language.

    Returns (sent, failed) delivery counts. Locale comes from user_profiles.language
    (never auth.users — that schema is Supabase-only and absent locally/in CI). That
    column is populated by ``ensure_user_profile`` (app/core/security.py), which syncs
    it from the JWT's ``user_metadata.preferred_locale`` on each authenticated request;
    it defaults to 'vi' for members who haven't set a locale."""
    result = await db.execute(
        text("""
            SELECT ucr.user_id, t.token, t.device_platform,
                   COALESCE(up.language, 'vi') AS locale
            FROM public.user_clan_roles ucr
            JOIN public.user_fcm_tokens t ON t.user_id = ucr.user_id
            LEFT JOIN public.user_profiles up ON up.id = ucr.user_id
            WHERE ucr.clan_id = :clan_id
              AND ucr.is_approved = true
              AND (up.is_active IS DISTINCT FROM false)
              AND (CAST(:exclude AS uuid) IS NULL OR ucr.user_id != CAST(:exclude AS uuid))
        """),
        {"clan_id": clan_id, "exclude": exclude_user_id},
    )
    rows = result.mappings().all()
    if not rows:
        return 0, 0

    # Batch with send_each (500 messages/call) instead of one blocking HTTPS
    # round-trip per token — a few hundred devices x several events was putting
    # the scheduler job runtime into minutes while it held the advisory lock.
    data = kwargs.pop("data", None)
    messages = [
        _build_message(row["token"], title_key, body_key, row["locale"], data, **kwargs)
        for row in rows
    ]
    sent = 0
    failed = 0
    for start in range(0, len(messages), _FCM_BATCH_LIMIT):
        chunk = messages[start : start + _FCM_BATCH_LIMIT]
        try:
            batch = await asyncio.to_thread(messaging.send_each, chunk)
        except Exception as e:
            logger.error("FCM batch send failed: %s (%d messages)", e, len(chunk))
            failed += len(chunk)
            continue
        for message, resp in zip(chunk, batch.responses, strict=True):
            if resp.success:
                sent += 1
                continue
            failed += 1
            if isinstance(resp.exception, messaging.UnregisteredError):
                await _remove_invalid_token(message.token, db)
            else:
                logger.error("FCM send failed: %s (token=%s)", resp.exception, message.token[:20])
    return sent, failed
