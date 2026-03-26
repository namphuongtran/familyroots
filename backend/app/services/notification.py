"""FCM push notification sender service."""

import logging
import uuid
from typing import Any

import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.translator import t

logger = logging.getLogger(__name__)

_firebase_app: firebase_admin.App | None = None


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
    """Remove an unregistered FCM token from the database."""
    if db is None:
        return
    await db.execute(
        text("DELETE FROM public.user_fcm_tokens WHERE token = :token"),
        {"token": fcm_token},
    )
    await db.commit()


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
        message = messaging.Message(
            notification=messaging.Notification(
                title=t(title_key, **kwargs),
                body=t(body_key, **kwargs),
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
        messaging.send(message)
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
) -> None:
    """Broadcast a notification to all approved members of a clan.

    Fetches each user's preferred_locale for localized messages.
    """
    result = await db.execute(
        text("""
            SELECT ucr.user_id, t.token, t.device_platform,
                   COALESCE(
                       au.raw_user_meta_data->>'preferred_locale',
                       'vi'
                   ) AS locale
            FROM public.user_clan_roles ucr
            JOIN public.user_fcm_tokens t ON t.user_id = ucr.user_id
            LEFT JOIN auth.users au ON au.id = ucr.user_id
            WHERE ucr.clan_id = :clan_id
              AND ucr.is_approved = true
              AND (:exclude IS NULL OR ucr.user_id != :exclude)
        """),
        {"clan_id": clan_id, "exclude": exclude_user_id},
    )
    rows = result.mappings().all()

    for row in rows:
        await send_push_notification(
            fcm_token=row["token"],
            title_key=title_key,
            body_key=body_key,
            locale=row["locale"],
            db=db,
            **kwargs,
        )
