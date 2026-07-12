"""Retention purge for soft-deleted documents (ADR-019).

Daily job: documents with is_deleted = true AND deleted_at older than
DOCUMENT_RETENTION_DAYS are permanently removed. Per item, the order is
claim row -> delete blob -> commit (owner decision 2026-07-12, supersedes an
earlier blob-first draft):

1. A guarded `DELETE ... WHERE id = :id AND is_deleted = true AND
   deleted_at < :cutoff` claims the row inside the still-open transaction.
   Only a row that still matches the eligibility predicate is taken. If a
   restore landed between the batch SELECT snapshot and this claim, rowcount
   is 0 — nothing was claimed, so the blob must not be touched; roll back and
   move to the next row.
2. Only once the row is claimed does the blob get deleted.
3. Only once the blob delete succeeds does the transaction commit.

This ordering means a crash or exception anywhere in the item rolls back the
claim, so the row survives to be retried next run — never a silent, partial
purge. A blob that was actually deleted moments before a crash simply
surfaces as "already gone" on the retry (the storage adapter treats
confirmed-not-found as success), so the row is purged cleanly next time —
never a permanent orphan blob. And a restore that races the sweep either
lands before this row's claim (rowcount 0, skip, blob and row both survive)
or blocks on the claim's row lock and loses cleanly once the claim commits
(the row is gone; the restore call then 404s) — never a document silently
destroyed out from under a user who just restored it.

Per-item isolation: one failure never stops the sweep. Advisory-locked on its
own key so multi-replica deployments run it once.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.engine import CursorResult
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
                            "WHERE is_deleted = true AND deleted_at < :cutoff "
                            "ORDER BY deleted_at ASC"
                        ),
                        {"cutoff": cutoff},
                    )
                )
                .mappings()
                .all()
            )
            for row in rows:
                try:
                    claim = cast(
                        "CursorResult[Any]",
                        await db.execute(
                            text(
                                "DELETE FROM public.documents WHERE id = :id "
                                "AND is_deleted = true AND deleted_at < :cutoff"
                            ),
                            {"id": row["id"], "cutoff": cutoff},
                        ),
                    )
                    if claim.rowcount == 0:
                        # Restored (or already purged by a concurrent run) since
                        # the batch SELECT snapshot above — nothing claimed, so
                        # the blob must not be touched. Clean rollback + skip.
                        await db.rollback()
                        logger.info(
                            "Document %s no longer eligible (restored or already "
                            "purged) — skipping",
                            row["id"],
                        )
                        continue
                    await storage.delete(row["storage_path"])
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
