"""notification_log.sent_on — explicit platform-day dedup column + matching index.

The scheduler dedup query filters (event_id, notification_type, platform-tz
day of created_at), but the only candidate index was
(user_id, event_id, notification_type, created_at AT TIME ZONE 'UTC') —
leading column absent from the query and a different timezone expression, so
every per-event dedup check sequential-scanned notification_log (which grows
forever), and the unique backstop enforced a different day boundary (UTC)
than the query checked (VN).

`sent_on` is the platform-tz calendar day the scheduler decided to send for,
stamped explicitly on insert. The unique index matches the query exactly:
(event_id, notification_type, sent_on).

Revision ID: 017_notification_sent_on
Revises: 016_document_soft_delete
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "017_notification_sent_on"
down_revision: str | None = "016_document_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notification_log", sa.Column("sent_on", sa.Date(), nullable=True))
    # Legacy rows: backfill from created_at in the platform zone (the zone the
    # dedup query has always used). New rows are stamped by the scheduler.
    op.execute(
        "UPDATE notification_log "
        "SET sent_on = CAST(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh' AS date)"
    )
    op.execute("DROP INDEX IF EXISTS idx_notification_log_dedup")
    op.execute(
        "CREATE UNIQUE INDEX idx_notification_log_dedup "
        "ON notification_log (event_id, notification_type, sent_on)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_notification_log_dedup")
    op.execute(
        "CREATE UNIQUE INDEX idx_notification_log_dedup "
        "ON notification_log (user_id, event_id, notification_type, "
        "CAST(created_at AT TIME ZONE 'UTC' AS date))"
    )
    op.drop_column("notification_log", "sent_on")
