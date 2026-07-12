"""Data-integrity hardening: OCC version columns + spouse_order uniqueness.

- persons / marriages / parent_child gain `version INTEGER NOT NULL DEFAULT 1`
  (optimistic concurrency; PATCH requires expected_version, see ADR-017).
- Partial unique index guarantees a person1's ACTIVE marriages have distinct
  spouse_order (vợ cả/hai/ba ordering is deterministic). "Active" means any
  status other than divorced (married, widowed, separated) — matching
  ``has_active_marriage``'s definition of active.
- Pre-check: if existing data already violates spouse_order uniqueness, FAIL
  with the offending rows listed — the operator must resolve history manually;
  we never silently renumber a gia phả.

Revision ID: 015_data_integrity
Revises: 014_drop_date_approx
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "015_data_integrity"
down_revision: str | None = "014_drop_date_approx"
branch_labels = None
depends_on = None

_TABLES = ("persons", "marriages", "parent_child")


def upgrade() -> None:
    conn = op.get_bind()
    dupes = conn.execute(
        sa.text(
            """SELECT created_by_clan_id, person1_id, spouse_order, COUNT(*)
               FROM marriages
               WHERE spouse_order IS NOT NULL AND is_deleted = false
                 AND status <> 'divorced'
               GROUP BY created_by_clan_id, person1_id, spouse_order
               HAVING COUNT(*) > 1"""
        )
    ).fetchall()
    if dupes:
        raise RuntimeError(
            "spouse_order duplicates exist; resolve before migrating: "
            + "; ".join(f"clan={r[0]} person1={r[1]} order={r[2]} x{r[3]}" for r in dupes)
        )

    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )

    op.execute(
        """CREATE UNIQUE INDEX uq_marriages_spouse_order
           ON marriages (created_by_clan_id, person1_id, spouse_order)
           WHERE spouse_order IS NOT NULL AND is_deleted = false
             AND status <> 'divorced'"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_marriages_spouse_order")
    for table in _TABLES:
        op.drop_column(table, "version")
