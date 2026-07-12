"""Retention purge for soft-deleted documents (ADR-019).

Daily job: documents with is_deleted = true AND deleted_at older than
DOCUMENT_RETENTION_DAYS lose their storage blob, then their row — in that
order (a failed blob delete leaves the row for the next run; the reverse
would orphan blobs). Per-item isolation: one failure never stops the sweep.
Advisory-locked on its own key so multi-replica deployments run it once.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.infrastructure.storage.supabase_adapter import SupabaseStorageAdapter

logger = logging.getLogger(__name__)

# Own advisory-lock key (distinct from the anniversary job's 728_115_001) so the
# two jobs never contend with each other, only with concurrent runs of themselves.
_PURGE_LOCK_KEY = 728_115_002


async def purge_expired_documents(now: datetime | None = None) -> None:
    """Permanently remove soft-deleted documents past DOCUMENT_RETENTION_DAYS.

    ``now`` is injectable only for deterministic tests; production always leaves it
    None so the cutoff is the real current instant.

    Lock topology mirrors send_anniversary_notifications (C2): the advisory lock
    lives on ONE dedicated connection held for the whole job; the working session
    is bound to that same connection so mid-job commits can't release it back to
    the pool and strand the lock. The finally block rolls back before unlocking so
    a failed job can't mask its own error with InFailedSqlTransaction.
    """
    from app.core.database import engine

    if now is None:
        now = datetime.now(UTC)
    cutoff = now - timedelta(days=settings.DOCUMENT_RETENTION_DAYS)
    storage = SupabaseStorageAdapter()

    async with engine.connect() as conn:
        acquired = await conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": _PURGE_LOCK_KEY}
        )
        if not acquired.scalar():
            logger.info("Document purge lock held elsewhere — skipping")
            await conn.rollback()
            return
        # End the autobegun transaction the lock SELECT opened (the
        # session-level advisory lock survives commit). See send_anniversary_notifications
        # for the full rationale.
        await conn.commit()

        db = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            rows = (
                (
                    await db.execute(
                        text(
                            "SELECT id, storage_path FROM public.documents "
                            "WHERE is_deleted = true AND deleted_at < :cutoff"
                        ),
                        {"cutoff": cutoff},
                    )
                )
                .mappings()
                .all()
            )
            for row in rows:
                try:
                    await storage.delete(row["storage_path"])  # False (missing) is fine
                    await db.execute(
                        text("DELETE FROM public.documents WHERE id = :id"), {"id": row["id"]}
                    )
                    await db.commit()
                    logger.info("Purged expired document %s", row["id"])
                except Exception:
                    logger.exception(
                        "Purge failed for document %s — will retry next run", row["id"]
                    )
                    await db.rollback()
                    continue
        finally:
            # Roll back any open/aborted transaction BEFORE unlocking: the
            # session-level advisory lock survives rollback, and unlocking on
            # an aborted tx would raise and mask the job's real error.
            await db.rollback()
            await db.close()
            await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _PURGE_LOCK_KEY})
            await conn.commit()
