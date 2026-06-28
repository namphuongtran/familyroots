"""Exclude soft-deleted rows from the relationship unique indexes.

Soft-deleting a marriage / parent-child edge left the row occupying the unique
index, so re-creating the same edge after deletion failed with a raw IntegrityError
(2026-06-28 design review). Add `is_deleted = false` to both partial unique indexes
so a soft-deleted edge no longer blocks re-creation, while still preventing
duplicate *live* edges.

Revision ID: 006_softdelete_unique_indexes
Revises: 005_tree_functions_clan_scoped
"""

from __future__ import annotations

from alembic import op

revision: str = "006_softdelete_unique_indexes"
down_revision: str | None = "005_tree_functions_clan_scoped"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_marriages_unique_pair")
    op.execute(
        "CREATE UNIQUE INDEX idx_marriages_unique_pair "
        "ON marriages (LEAST(person1_id, person2_id), GREATEST(person1_id, person2_id), status) "
        "WHERE status = 'married' AND is_deleted = false"
    )
    op.execute("DROP INDEX IF EXISTS idx_parent_child_unique_edge")
    op.execute(
        "CREATE UNIQUE INDEX idx_parent_child_unique_edge "
        "ON parent_child (parent_id, child_id, relationship_type) "
        "WHERE is_deleted = false"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_parent_child_unique_edge")
    op.execute(
        "CREATE UNIQUE INDEX idx_parent_child_unique_edge "
        "ON parent_child (parent_id, child_id, relationship_type)"
    )
    op.execute("DROP INDEX IF EXISTS idx_marriages_unique_pair")
    op.execute(
        "CREATE UNIQUE INDEX idx_marriages_unique_pair "
        "ON marriages (LEAST(person1_id, person2_id), GREATEST(person1_id, person2_id), status) "
        "WHERE status = 'married'"
    )
