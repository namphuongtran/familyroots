"""audit_logs: bare (created_at DESC, id DESC) index for the platform-wide recent scan.

The platform-admin audit log lists cross-clan events newest-first (M14). In its
unfiltered form (no clan_id filter — all clans' rows), the ORDER BY (created_at DESC,
id DESC) + the (created_at, id) keyset cursor had no supporting index — only per-clan /
per-actor composites existed (001:853-854) — so the query fell back to a full scan +
sort that worsened as audit_logs grew. This adds the missing index. No table change;
reversible.

Revision ID: 025_audit_logs_created_at_index
Revises: 024_kinship_exclude_divorced
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "025_audit_logs_created_at_index"
down_revision: str | None = "024_kinship_exclude_divorced"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_audit_logs_created_at",
        "audit_logs",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_audit_logs_created_at", table_name="audit_logs")
