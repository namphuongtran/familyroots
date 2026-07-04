"""Drop the updated_at trigger on change_requests (it has no updated_at column).

Migration 001 attached ``trg_change_requests_updated_at`` (which runs
``NEW.updated_at = NOW()``) to change_requests inside the shared trigger loop, but
that table is created with ``created_at`` only — by design, change requests are
immutable-append records. Any UPDATE on the table therefore errors at the DB
(`record "new" has no field "updated_at"`), which would break the entire
change-request approval workflow the moment it is wired up (currently dormant —
only the Pydantic schema references the table). Drop the mis-attached trigger.

Revision ID: 008_drop_change_req_trigger
Revises: 007_clan_scoped_edge_unique
"""

from __future__ import annotations

from alembic import op

revision: str = "008_drop_change_req_trigger"
down_revision: str | None = "007_clan_scoped_edge_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_change_requests_updated_at ON change_requests")


def downgrade() -> None:
    # Restore the prior (broken-by-design) state for a faithful round-trip.
    op.execute(
        "CREATE TRIGGER trg_change_requests_updated_at "
        "BEFORE UPDATE ON change_requests "
        "FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"
    )
