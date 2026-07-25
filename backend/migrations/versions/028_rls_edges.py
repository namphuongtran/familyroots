"""RLS layer-2 Phase 3: enable clan-isolation RLS on parent_child + marriages (ADR-008).

The tree edges — keyed by NOT-NULL ``created_by_clan_id`` — are the isolation-critical
tables the tree CTEs traverse (the M10 concern). Policy mirrors documents/events but on
``created_by_clan_id``: read/write only rows whose owning clan == the ``app.clan_id`` GUC;
unset GUC → zero rows / rejected write (fail closed).

Safe under the seam because the tree SQL functions (``find_relationship_path``,
``get_ancestors_flat``, the descendants CTE) and the parent_child BEFORE-ROW trigger
(``parent_child_clan_lock``/``parent_child_integrity_guard``) are all SECURITY INVOKER
and clan-scoped by ``p_clan_id`` / ``created_by_clan_id`` = the request's clan = the GUC,
so the RLS predicate is redundant with their own filter (verified by
``test_rls_phase3_edges``). System paths bypass. Grants already exist (002 + 026).
Reversible (drop policy + disable).

Revision ID: 028_rls_edges
Revises: 027_rls_events_branches
"""

from __future__ import annotations

from alembic import op

revision: str = "028_rls_edges"
down_revision: str | None = "027_rls_events_branches"
branch_labels = None
depends_on = None

_TABLES = ("parent_child", "marriages")
_PREDICATE = "created_by_clan_id = nullif(current_setting('app.clan_id', true), '')::uuid"


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_clan_isolation ON {table}")
        op.execute(
            f"CREATE POLICY {table}_clan_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_clan_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
