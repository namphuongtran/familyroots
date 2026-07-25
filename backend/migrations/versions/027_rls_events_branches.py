"""RLS layer-2 Phase 2: enable clan-isolation RLS on events + branches (SP-3, ADR-008).

Extends the runtime seam (Phase 1, migration 026 + app/core/rls.py) to two more
clan-owned tables. Both are keyed by a NOT-NULL ``clan_id`` and are queried only by
request handlers (which run under the request role with ``app.clan_id`` set) — the
cross-clan anniversary scheduler reads ``events`` through a privileged SYSTEM session
(no RLS seam), so it still scans all clans. Policy mirrors ``documents_clan_isolation``:
``clan_id = <app.clan_id GUC>`` for both USING (reads) and WITH CHECK (writes);
an unset GUC → NULL → zero rows / rejected write (fail closed). Grants already exist
(migration 002 table CRUD + 026 functions). Reversible (drop policy + disable).

Revision ID: 027_rls_events_branches
Revises: 026_rls_activation_grants
"""

from __future__ import annotations

from alembic import op

revision: str = "027_rls_events_branches"
down_revision: str | None = "026_rls_activation_grants"
branch_labels = None
depends_on = None

_TABLES = ("events", "branches")
_PREDICATE = "clan_id = nullif(current_setting('app.clan_id', true), '')::uuid"


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
