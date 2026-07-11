"""Drop the retired `persons.birth_date_approx` / `persons.death_date_approx` columns.

HistoricalDate contract, Task 5 (final): every reader in `app/` has switched from the
boolean `*_approx` flags to the richer `*_precision`/`*_display` columns added by
migration 012 and backfilled from `approx` at that time (`approx=true` -> 'circa').
`approx` has had no readers or writers since Task 5's application-layer changes
landed, so it is safe to drop.

`downgrade()` re-adds both columns (nullable BOOLEAN, `server_default false`) so a
rollback restores the schema shape — but the ORIGINAL per-row `approx` values are
NOT recoverable (the CASE backfill in migration 012 was one-directional: `precision`
does not encode whether the source flag was true), so a downgrade after this
migration lands every existing row's `approx` back to `false` regardless of its
prior value. This mirrors the codebase's other soft-delete/audit-column migrations
that don't attempt data time-travel on downgrade — no other migration in this
history relies on `approx` being reconstructed correctly.

Revision ID: 014_drop_date_approx
Revises: 013_tree_date_precision
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "014_drop_date_approx"
down_revision: str | None = "013_tree_date_precision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("persons", "birth_date_approx")
    op.drop_column("persons", "death_date_approx")


def downgrade() -> None:
    op.add_column(
        "persons",
        sa.Column("death_date_approx", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "persons",
        sa.Column("birth_date_approx", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
