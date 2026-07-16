"""Events: soft-delete + optimistic concurrency + person FK SET NULL (ADR-022).

Events were the one aggregate left with destructive delete and no version
column: a misclick permanently destroyed a giỗ record (the data loss ADR-019
fixed for documents), and concurrent PATCHes silently last-write-wins'd
(the gap ADR-017 closed for persons/marriages/parent_child).

- is_deleted/deleted_at/deleted_by: soft-delete with restore, matching
  documents (migration 016).
- version: OCC token, matching persons/marriages (migration 015).
- events.person_id ON DELETE CASCADE -> SET NULL: persons are never
  hard-deleted in the app, but a manual DELETE FROM persons must not
  silently destroy the giỗ records referencing them — documents already
  use SET NULL for the same reason.

Revision ID: 020_event_soft_delete_occ
Revises: 019_path_bfs_visited
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "020_event_soft_delete_occ"
down_revision: str | None = "019_path_bfs_visited"
branch_labels = None
depends_on = None


def _repoint_person_fk(ondelete: str) -> None:
    insp = sa.inspect(op.get_bind())
    matched = [
        fk
        for fk in insp.get_foreign_keys("events")
        if fk.get("referred_table") == "persons"
        and "person_id" in fk.get("constrained_columns", [])
    ]
    if len(matched) != 1:
        raise RuntimeError(f"expected exactly one persons FK on events.person_id: {matched}")
    fk = matched[0]
    op.drop_constraint(fk["name"], "events", type_="foreignkey")
    op.create_foreign_key(fk["name"], "events", "persons", ["person_id"], ["id"], ondelete=ondelete)


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("events", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("deleted_by", sa.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "events", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.execute("CREATE INDEX idx_events_is_deleted ON events (is_deleted) WHERE is_deleted = false")
    _repoint_person_fk("SET NULL")


def downgrade() -> None:
    _repoint_person_fk("CASCADE")
    op.execute("DROP INDEX IF EXISTS idx_events_is_deleted")
    op.drop_column("events", "version")
    op.drop_column("events", "deleted_by")
    op.drop_column("events", "deleted_at")
    op.drop_column("events", "is_deleted")
