"""RLS layer-2 Phase 5: enable clan-isolation RLS on change_requests (S-008, ADR-008).

``change_requests`` is keyed by a NOT-NULL ``clan_id``
(``app/models/change_request.py:19``), so the migration 027 template applies unchanged:
``clan_id = <app.clan_id GUC>`` on both USING (reads) and WITH CHECK (writes). An unset
GUC yields NULL, which yields zero rows and a rejected write (fail closed).

Why this table matters more than its size suggests: a change request holds a *proposed*
value for clan data before anyone approves it (ADR-037), so a leak here exposes edits
that were never accepted. Until this migration the repository's explicit ``clan_id``
predicate was its only enforced isolation.

Every reader and writer is a clan-scoped request handler on ``get_db`` (the RLS request
session — see ``app/infrastructure/dependencies.py`` ``get_change_request_command_handler``
and ``get_change_request_query_handler``), so the GUC is always set for them. No system
session and no unauthenticated path touches this table, so nothing legitimately needs the
bypass. Grants already exist (migration 002 table CRUD + 026 functions). Reversible
(drop policy + disable).

Unlike ``persons`` (ADR-038), the ``RETURNING`` clause SQLAlchemy appends to the INSERT
is safe here: this is a single permissive ALL policy, so the row a fresh INSERT returns is
matched against the same ``clan_id = GUC`` predicate that just accepted it. Pinned by
``test_rls_phase5_change_requests::test_orm_insert_with_returning_succeeds``.

Revision ID: 030_rls_change_requests
Revises: 029_rls_persons
"""

from __future__ import annotations

from alembic import op

revision: str = "030_rls_change_requests"
down_revision: str | None = "029_rls_persons"
branch_labels = None
depends_on = None

_TABLE = "change_requests"
_PREDICATE = "clan_id = nullif(current_setting('app.clan_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {_TABLE}_clan_isolation ON {_TABLE}")
    op.execute(
        f"CREATE POLICY {_TABLE}_clan_isolation ON {_TABLE} "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_TABLE}_clan_isolation ON {_TABLE}")
    op.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
