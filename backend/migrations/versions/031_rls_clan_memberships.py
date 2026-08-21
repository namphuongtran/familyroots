"""RLS layer-2 Phase 6: enable clan-isolation RLS on clan_memberships (S-009, ADR-008).

``clan_memberships`` is keyed by a NOT-NULL ``clan_id``
(``app/models/clan_membership.py:28``), so the migration 027 template applies unchanged:
``clan_id = <app.clan_id GUC>`` on both USING (reads) and WITH CHECK (writes). An unset
GUC yields NULL, which yields zero rows and a rejected write (fail closed).

Why this table matters: it is the person-to-clan link. ``persons`` itself is already
RLS-protected (migration 029), but the membership row carries ``generation``,
``is_founder`` and ``branch_id`` — the clan's own structural claims about that person —
and every clan-scoped person query joins through it. A missed filter here leaks who
belongs to a clan, which is membership data even when the person row stays hidden.

**Every request-path reader and writer of this table runs on a clan-scoped route.**
Checked one by one against the routes that reach them, on 2026-08-22:
``person_repository`` / ``person_query_port`` (persons + change-request routes),
``tree_repository``, ``branch_repository``, ``document_repository``,
``event_repository``, ``relationship_repository``, ``change_request_repository``,
``clan_repository`` and ``export_query_port`` are all wired to ``get_db`` (the RLS
request session) from handlers whose routes carry ``Depends(get_current_clan_id)``, so
the GUC is always set before they run. ``platform_admin_query_port`` also reads this
table (``app/infrastructure/persistence/platform_admin_query_port.py:71``) but is wired
to ``get_system_db`` (``app/infrastructure/dependencies.py:174``) — the privileged
cross-clan session, which bypasses RLS exactly as it already does for ``persons``.
The auth/login path never touches this table: it reads ``user_clan_roles``, a different
table (``app/infrastructure/persistence/auth_repository.py:100-135``).

**``clan_invitations`` is deliberately NOT included, although seed S-009 names it.**
``POST /api/v1/invitations/{token}/accept`` (``app/api/v1/invitations.py:89-102``) has no
``Depends(get_current_clan_id)`` — the invitee is not a member of the clan yet, so there
is no clan to select — but its handler is wired to ``get_db``
(``app/infrastructure/dependencies.py:336-340``), the RLS request session. The very first
thing accept does is ``get_by_token`` (``invitation_repository.py:53-58``), a lookup with
no ``clan_id`` predicate. Under this policy that read returns zero rows and every accept
would 404 with ``invitation.not_found``. Choosing between "move the accept path to the
privileged session" and "keep RLS off this table" changes the isolation posture of a
write path, so it is a decision with its own ADR, not part of this migration.
``tests/integration/test_invitation_accept_no_clan_context.py`` pins the break so the
next agent sees it rather than shipping it.

Grants already exist (migration 002 table CRUD + 026 functions). Reversible (drop policy
+ disable).

Revision ID: 031_rls_clan_memberships
Revises: 030_rls_change_requests
"""

from __future__ import annotations

from alembic import op

revision: str = "031_rls_clan_memberships"
down_revision: str | None = "030_rls_change_requests"
branch_labels = None
depends_on = None

_TABLES = ("clan_memberships",)
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
