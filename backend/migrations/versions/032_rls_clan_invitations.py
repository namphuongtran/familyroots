"""RLS layer-2 Phase 7: enable clan-isolation RLS on clan_invitations (S-043, ADR-048).

``clan_invitations`` is keyed by a NOT-NULL ``clan_id``
(``app/models/clan_invitation.py:27-31``), so the migration 027 template applies unchanged:
``clan_id = <app.clan_id GUC>`` on both USING (reads) and WITH CHECK (writes). An unset GUC
yields NULL, which yields zero rows and a rejected write (fail closed).

**Migration 031 deliberately left this table out, and ADR-048 is what changed.** The
obstacle was never the table. It was that all four invitation routes ran on ``get_db``, and
one of them — ``POST /api/v1/invitations/{token}/accept`` — has no clan context by design:
the invitee is not a member of the clan yet, so ``get_current_clan_id`` cannot be declared
and the GUC stays empty for the whole request. Under this policy its very first query,
``get_by_token`` (``invitation_repository.py:53-58``, no ``clan_id`` predicate because the
token IS the authorization), would return zero rows and every accept would answer
``invitation.not_found``.

ADR-048 moved that ONE route to its own provider on the privileged system session
(``get_invitation_accept_handler``, ``app/infrastructure/dependencies.py:358-362``). The
other three keep the seam and are what this policy protects:

* create — ``app/api/v1/invitations.py:42``, ``get_invitation_command_handler`` on ``get_db``
* list — ``app/api/v1/invitations.py:62``, ``get_invitation_query_handler`` on ``get_db``
* revoke — ``app/api/v1/invitations.py:76``, ``get_invitation_command_handler`` on ``get_db``

Each of them already filters by ``clan_id`` in the repository and each route rejects a
``clan_id`` that is not the caller's active clan (``invitations.py:44``, ``:64``, ``:78``).
This policy is the second layer behind those filters, not a replacement for them.

The accept path keeps ONE layer, the token, and ADR-048 says so in those words rather than
claiming a coverage it does not have. ``tests/unit/api/test_invitation_accept_session_wiring.py``
fails if anyone re-points accept at ``get_db``, and
``tests/integration/test_invitation_accept_no_clan_context.py`` shows what would happen if
they did.

Grants already exist (migration 002 table CRUD + 026 functions). Reversible (drop policy
+ disable).

Revision ID: 032_rls_clan_invitations
Revises: 031_rls_clan_memberships
"""

from __future__ import annotations

from alembic import op

revision: str = "032_rls_clan_invitations"
down_revision: str | None = "031_rls_clan_memberships"
branch_labels = None
depends_on = None

_TABLES = ("clan_invitations",)
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
