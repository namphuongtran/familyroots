"""APScheduler job definitions — daily anniversary notification cron."""

import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    """Configure and start the cron scheduler."""
    scheduler.add_job(
        func=send_anniversary_notifications,
        trigger=CronTrigger(hour=settings.NOTIFICATION_CRON_HOUR, minute=0),
        id="anniversary_notifications",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("Scheduler started — cron at hour=%s", settings.NOTIFICATION_CRON_HOUR)


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")


async def send_anniversary_notifications() -> None:
    """Daily job: find events with upcoming anniversaries and send FCM notifications.

    Deduplicates via the ``notification_log`` table to avoid re-sending
    if the server restarts within the same day.
    """
    from app.core.database import AsyncSessionLocal
    from app.services.notification import send_to_clan

    today = date.today()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT
                    e.id AS event_id,
                    e.clan_id,
                    e.event_type,
                    e.title,
                    e.member_id,
                    m.full_name AS member_name,
                    e.notify_days_before,
                    CASE
                        WHEN (MAKE_DATE(EXTRACT(YEAR FROM CURRENT_DATE)::INT,
                                        EXTRACT(MONTH FROM e.event_date)::INT,
                                        EXTRACT(DAY FROM e.event_date)::INT)
                              >= CURRENT_DATE)
                        THEN MAKE_DATE(EXTRACT(YEAR FROM CURRENT_DATE)::INT,
                                       EXTRACT(MONTH FROM e.event_date)::INT,
                                       EXTRACT(DAY FROM e.event_date)::INT)
                        ELSE MAKE_DATE(EXTRACT(YEAR FROM CURRENT_DATE)::INT + 1,
                                       EXTRACT(MONTH FROM e.event_date)::INT,
                                       EXTRACT(DAY FROM e.event_date)::INT)
                    END AS next_occurrence
                FROM public.events e
                LEFT JOIN public.members m ON m.id = e.member_id
                WHERE e.is_recurring = true
            """)
        )
        events = result.mappings().all()

        for event in events:
            next_occ = event["next_occurrence"]
            days_until = (next_occ - today).days

            if days_until != event["notify_days_before"]:
                continue

            # Dedup: skip if already sent today for this event
            dedup = await db.execute(
                text("""
                    SELECT 1 FROM public.notification_log
                    WHERE event_id = :event_id
                      AND notification_type = :ntype
                      AND DATE(created_at) = CURRENT_DATE
                    LIMIT 1
                """),
                {"event_id": event["event_id"], "ntype": event["event_type"]},
            )
            if dedup.first():
                continue

            await send_to_clan(
                clan_id=event["clan_id"],
                title_key=f"notification.{event['event_type']}.title",
                body_key=f"notification.{event['event_type']}.body",
                db=db,
                name=event["member_name"] or event["title"],
                days=event["notify_days_before"],
            )

            await db.execute(
                text("""
                    INSERT INTO public.notification_log
                        (clan_id, event_id, user_id,
                         notification_type, title, body, status, sent_at)
                    VALUES (:clan_id, :event_id, '00000000-0000-0000-0000-000000000000',
                            :ntype, :title, '', 'sent', NOW())
                """),
                {
                    "clan_id": event["clan_id"],
                    "event_id": event["event_id"],
                    "ntype": event["event_type"],
                    "title": event["title"],
                },
            )
            await db.commit()
