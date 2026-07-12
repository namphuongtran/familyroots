"""Documents move from hard-delete to soft-delete (ADR-019, data-safety PR1).

The entity's mark_deleted() existed but only emitted an event — the table never
had soft-delete columns and the repository issued a physical DELETE + permanent
blob removal. For irreplaceable scanned heritage documents that is data loss on
a misclick. These columns give documents the same recoverable-delete semantics
as persons; a retention purge job removes blob+row after DOCUMENT_RETENTION_DAYS.

Revision ID: 016_document_soft_delete
Revises: 015_data_integrity
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "016_document_soft_delete"
down_revision: str | None = "015_data_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("documents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("deleted_by", UUID(as_uuid=True), nullable=True))
    op.execute(
        "CREATE INDEX idx_documents_is_deleted ON documents (is_deleted) WHERE is_deleted = false"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_documents_is_deleted")
    op.drop_column("documents", "deleted_by")
    op.drop_column("documents", "deleted_at")
    op.drop_column("documents", "is_deleted")
