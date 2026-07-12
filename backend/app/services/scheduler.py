"""APScheduler job definitions — daily anniversary notification cron."""

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.document_purge import purge_expired_documents
from app.services.lunar_calendar import next_lunar_anniversary

logger = logging.getLogger(__name__)

# Fixed key for the cross-replica advisory lock guarding the anniversary job.
_JOB_LOCK_KEY = 728_115_001

# One authoritative clock for the whole scheduler (see Settings.SCHEDULER_TIMEZONE).
_TZ = ZoneInfo(settings.SCHEDULER_TIMEZONE)

scheduler = AsyncIOScheduler(timezone=_TZ)


def start_scheduler() -> None:
    """Configure and start the cron scheduler."""
    scheduler.add_job(
        func=send_anniversary_notifications,
        # Explicit tz so "hour=7" means 07:00 in the platform zone regardless of the
        # container's system timezone.
        trigger=CronTrigger(hour=settings.NOTIFICATION_CRON_HOUR, minute=0, timezone=_TZ),
        id="anniversary_notifications",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        func=purge_expired_documents,
        trigger=CronTrigger(hour=settings.NOTIFICATION_CRON_HOUR, minute=30, timezone=_TZ),
        id="document_purge",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info(
        "Scheduler started — cron at hour=%s %s",
        settings.NOTIFICATION_CRON_HOUR,
        settings.SCHEDULER_TIMEZONE,
    )


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")


async def send_anniversary_notifications(today: date | None = None) -> None:
    """Daily job: find events with upcoming anniversaries and send FCM notifications.

    Single clock (M4): ``today`` is computed once in the platform timezone and threaded
    into the SQL as ``:today``; the query contains no ``CURRENT_DATE``, so the occurrence
    math and the "is it N days away" gate can't disagree because the container's local
    date differs from the DB server's date.

    ``today`` CONTRACT: it is the logical run-date. Production always leaves it None so
    it is the real date in the platform zone (the cron fires once per that day). It is
    injectable only for deterministic tests, and callers MUST pass the real current
    date — the dedup below keys on the row's creation day, which equals ``today`` only
    when ``today`` is "now". Replaying/backfilling a PAST ``today`` would therefore not
    be dedup-protected (it would re-send); supporting backfill needs a dedicated
    ``notified_on date`` column keyed to ``today``, out of scope here.

    Lock topology (C2, seam-review-2026-07-04): the advisory lock lives on ONE
    dedicated connection held for the whole job; the working session is bound
    to that same connection, so mid-job commits can't release it back to the
    pool and strand the lock. The finally block rolls back before unlocking so
    a failed job can't mask its own error with InFailedSqlTransaction.
    """
    from app.core.database import engine
    from app.infrastructure.persistence.sql_dates import next_anniversary_sql
    from app.services.notification import send_to_clan

    if today is None:
        today = datetime.now(_TZ).date()
    tz_name = settings.SCHEDULER_TIMEZONE
    this_year = next_anniversary_sql("EXTRACT(YEAR FROM :today ::date)")
    next_year = next_anniversary_sql("EXTRACT(YEAR FROM :today ::date) + 1")

    async with engine.connect() as conn:
        acquired = await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _JOB_LOCK_KEY})
        if not acquired.scalar():
            logger.info("Anniversary job lock held by another instance — skipping this run")
            await conn.rollback()
            return
        # End the autobegun transaction the lock SELECT opened (the
        # session-level advisory lock survives commit). Otherwise the bound
        # session below would JOIN that transaction via savepoints and its
        # commits would not be durable until the connection commits.
        await conn.commit()

        db = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            result = await db.execute(
                text(f"""
                    SELECT
                        e.id AS event_id,
                        e.clan_id,
                        e.event_type,
                        e.title,
                        e.person_id,
                        p.full_name AS person_name,
                        e.notify_days_before,
                        CASE
                            WHEN {this_year} >= :today THEN {this_year}
                            ELSE {next_year}
                        END AS next_occurrence
                    FROM public.events e
                    LEFT JOIN public.persons p ON p.id = e.person_id
                    WHERE e.is_recurring = true
                      AND e.is_lunar_calendar = false
                      AND (e.person_id IS NULL OR p.is_deleted = false)
                """),
                {"today": today},
            )
            events = result.mappings().all()

            lunar_result = await db.execute(
                text("""
                    SELECT
                        e.id AS event_id,
                        e.clan_id,
                        e.event_type,
                        e.title,
                        e.person_id,
                        p.full_name AS person_name,
                        e.notify_days_before,
                        e.event_date
                    FROM public.events e
                    LEFT JOIN public.persons p ON p.id = e.person_id
                    WHERE e.is_recurring = true
                      AND e.is_lunar_calendar = true
                      AND (e.person_id IS NULL OR p.is_deleted = false)
                """)
            )
            lunar_events = lunar_result.mappings().all()

            for event in [*events, *lunar_events]:
                try:
                    # Solar rows already carry a precomputed next_occurrence (cheap SQL
                    # date math that cannot raise). Lunar rows carry only event_date —
                    # next_lunar_anniversary runs the lunar-conversion algorithm, which
                    # CAN raise on a pathological date. Computing it lazily HERE, inside
                    # this per-event try, means one bad lunar row hits the
                    # rollback-and-continue path below instead of aborting the whole
                    # run before any event (solar or lunar) is processed.
                    if "next_occurrence" in event:
                        next_occ = event["next_occurrence"]
                    else:
                        next_occ = next_lunar_anniversary(event["event_date"], today)
                    days_until = (next_occ - today).days
                    if days_until != event["notify_days_before"]:
                        continue

                    dedup = await db.execute(
                        text("""
                            SELECT 1 FROM public.notification_log
                            WHERE event_id = :event_id
                              AND notification_type = :ntype
                              AND DATE(created_at AT TIME ZONE :tz) = :today
                            LIMIT 1
                        """),
                        {
                            "event_id": event["event_id"],
                            "ntype": event["event_type"],
                            "tz": tz_name,
                            "today": today,
                        },
                    )
                    if dedup.first():
                        continue

                    sent, failed = await send_to_clan(
                        clan_id=event["clan_id"],
                        title_key=f"notification.{event['event_type']}.title",
                        body_key=f"notification.{event['event_type']}.body",
                        db=db,
                        name=event["person_name"] or event["title"],
                        days=event["notify_days_before"],
                    )
                    status = "sent" if sent > 0 else "failed"
                    error_message = None if sent > 0 else f"0/{sent + failed} delivered"

                    await db.execute(
                        text("""
                            INSERT INTO public.notification_log
                                (clan_id, event_id, user_id, notification_type,
                                 title, body, status, sent_at, error_message)
                            VALUES (:clan_id, :event_id,
                                    '00000000-0000-0000-0000-000000000000',
                                    :ntype, :title, '', :status, NOW(), :error_message)
                        """),
                        {
                            "clan_id": event["clan_id"],
                            "event_id": event["event_id"],
                            "ntype": event["event_type"],
                            "title": event["title"],
                            "status": status,
                            "error_message": error_message,
                        },
                    )
                    await db.commit()
                except Exception:
                    # One bad event must not abort the rest of the run. Roll back the
                    # aborted per-event tx so the next event's statements can run.
                    logger.exception("Notification failed for event %s", event.get("event_id"))
                    await db.rollback()
                    continue
        finally:
            # Roll back any open/aborted transaction BEFORE unlocking: the
            # session-level advisory lock survives rollback, and unlocking on
            # an aborted tx would raise and mask the job's real error.
            await db.rollback()
            await db.close()
            await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _JOB_LOCK_KEY})
            await conn.commit()
