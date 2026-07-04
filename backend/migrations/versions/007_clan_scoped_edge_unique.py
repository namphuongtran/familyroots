"""Make relationship edge-uniqueness per-clan.

Persons are global and shared M:N across clans (clan_memberships); a marriage /
parent-child edge is owned by exactly one clan (created_by_clan_id). The confirmed
data model lets each clan independently record its own edges for a shared person
(clan B linking an in-law does not touch clan A's tree). The prior unique indexes
(006) keyed only on the person pair, so two clans that share members could NOT both
record the same real-world edge — the second clan hit a raw IntegrityError. This
also underpins the clan-scoping of the relationship validator's duplicate/count
checks: with a global index, scoping the validator alone would let validation pass
and then collide on the index. Add created_by_clan_id to both partial unique indexes
so uniqueness is enforced within a clan, not across the whole platform.

Revision ID: 007_clan_scoped_edge_unique
Revises: 006_softdelete_unique_indexes
"""

from __future__ import annotations

from alembic import op

revision: str = "007_clan_scoped_edge_unique"
down_revision: str | None = "006_softdelete_unique_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_marriages_unique_pair")
    op.execute(
        "CREATE UNIQUE INDEX idx_marriages_unique_pair ON marriages "
        "(created_by_clan_id, LEAST(person1_id, person2_id), "
        "GREATEST(person1_id, person2_id), status) "
        "WHERE status = 'married' AND is_deleted = false"
    )
    op.execute("DROP INDEX IF EXISTS idx_parent_child_unique_edge")
    op.execute(
        "CREATE UNIQUE INDEX idx_parent_child_unique_edge ON parent_child "
        "(created_by_clan_id, parent_id, child_id, relationship_type) "
        "WHERE is_deleted = false"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_parent_child_unique_edge")
    op.execute(
        "CREATE UNIQUE INDEX idx_parent_child_unique_edge "
        "ON parent_child (parent_id, child_id, relationship_type) "
        "WHERE is_deleted = false"
    )
    op.execute("DROP INDEX IF EXISTS idx_marriages_unique_pair")
    op.execute(
        "CREATE UNIQUE INDEX idx_marriages_unique_pair "
        "ON marriages (LEAST(person1_id, person2_id), GREATEST(person1_id, person2_id), status) "
        "WHERE status = 'married' AND is_deleted = false"
    )
