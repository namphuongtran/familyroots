"""RLS layer-2 Phase 11: user_clan_roles takes per-command policies (S-052, ADR-050).

**This table does NOT take the migration-027 template, and the difference is the whole
decision.** ``user_clan_roles`` is the table the authorization gate reads, so a policy on
it does not merely hide data: it decides what a caller may do. The 027 template breaks it
in two directions at once, re-measured 2026-08-22 by seed S-052 by putting the table in a
copy of migration 035's table list and running
``tests/integration/test_rls_login_two_clans.py``:

* **Reads fail silently.** ``get_current_clan_id`` reads this table on the request session
  at ``app/core/security.py:249-254`` and only sets ``app.clan_id`` afterwards at ``:290``,
  so the predicate is NULL for its own read. ``SqlAlchemyAuthQueryPort.get_login_profile``
  (``auth_repository.py:120-137``) and ``SqlAlchemyMeQueryPort.list_clans``
  (``me_query_port.py:19-42``) read it before any clan exists to select. Measured:
  ``POST /auth/login`` answers 200 with ``clan_id: None`` (``AssertionError: {... 'clan_id':
  None ...}``) and ``GET /me/clans`` returns ``[]`` (``AssertionError: set()``). Nothing
  raises and nothing is logged.
* **Writes fail loudly.** ``SqlAlchemyAuthRepository.add_membership``
  (``auth_repository.py:69-88``) INSERTs on that same clan-less session, so a clan-keyed
  ``WITH CHECK`` compares ``<real clan> = NULL``. Measured on both onboard flows:
  ``psycopg.errors.InsufficientPrivilege: new row violates row-level security policy for
  table "user_clan_roles"``, surfacing as a 500.

What ships here instead
-----------------------
Per command, following the ADR-043 shape but with the halves reversed:

* ``SELECT`` — ``USING (true)``. Permissive **by decision**. Every clan-less reader above
  is a SELECT, and each one is cross-clan by design: the gate must list a user's clans
  before one can be chosen, and ``GET /me/clans`` is the clan switcher. Making this half
  clan-keyed requires moving those readers to the privileged session, which ADR-050
  § "Alternatives" rejects and prices.
* ``INSERT`` — ``WITH CHECK (true)``. Permissive for the same reason on the write side:
  ``POST /auth/onboard`` creates the caller's own membership with no clan selected, and on
  the ``create`` branch the clan does not exist until that request makes it.
* ``UPDATE`` and ``DELETE`` — clan-keyed on both halves, and this is what the migration is
  for. Measured 2026-08-22: the only UPDATE/DELETE statements against this table on a
  **request** session are four in ``app/infrastructure/persistence/clan_repository.py`` —
  ``approve_if_pending`` (``:148-154``), ``delete_role_by_id`` (``:182-187``),
  ``delete_if_pending`` (``:199-204``) and ``change_role_if`` (``:217-223``). **Every one of
  them is keyed on the primary key alone, with no ``clan_id`` predicate at all.** Their
  clan safety today rests entirely on ``ucr_id`` having come from the clan-filtered
  ``get_user_clan_role`` (``:31-39``) a few lines earlier in
  ``app/application/clan/handlers.py`` (``:59``, ``:97``, ``:130``, ``:172``). That is a
  read-then-write pair, not a filter, and it is exactly the class of thing layer 2 exists
  to catch. All four are reached only from ``/api/v1/clans/me/users/*`` routes, which carry
  ``Depends(get_current_clan_id)``, so the GUC is always set when they run.
  The fifth request-session mutation candidate, ``promote_if_pending``
  (``invitation_repository.py:149-170``), is called only from
  ``InvitationCommandHandler.accept`` (``app/application/invitation/handlers.py:102``),
  which ADR-048 moved onto the privileged session, so it bypasses.

So this table is **half covered, on purpose**: the commands that change what a caller may
do are clan-keyed at the database, and the commands that only read are not. That is the
opposite half from ``audit_logs`` (ADR-043), and the reason is that a record leaks by being
read while a capability leaks by being written.

One consequence for whoever tightens ``user_clan_roles_sel`` later
------------------------------------------------------------------
The permissive SELECT is also load-bearing for the INSERT, which is the ADR-038 trap
recurring. ``UserClanRole`` inherits ``TimestampMixin``, so SQLAlchemy appends ``RETURNING
user_clan_roles.created_at, user_clan_roles.updated_at`` to every insert, and Postgres
matches a ``RETURNING`` row against the **SELECT** policy. Measured 2026-08-22 by planting a
clan-keyed SELECT while leaving ``WITH CHECK (true)`` in place: both onboard flows still fail
with ``psycopg.errors.InsufficientPrivilege: new row violates row-level security policy for
table "user_clan_roles"``, even though the INSERT policy admitted the row. So tightening the
read half breaks the write half too, and the error names the wrong policy while doing it.

``ENABLE``, not ``FORCE``: the system session connects as a bypassing role. Grants already
exist (migration 002 table CRUD + 026 functions and sequences). Reversible.

Under RLS a command with **no** matching policy is denied for a non-bypass role, which is
why the permissive SELECT and INSERT policies are written out explicitly rather than
omitted. Omitting them would deny login, onboarding and every role check.

Revision ID: 036_rls_user_clan_roles
Revises: 035_rls_clan_settings
"""

from __future__ import annotations

from alembic import op

revision: str = "036_rls_user_clan_roles"
down_revision: str | None = "035_rls_clan_settings"
branch_labels = None
depends_on = None

# The migration-027 predicate, verbatim. An unset GUC → empty string → nullif → NULL →
# no row matches and no write is admitted (fail closed).
_PREDICATE = "clan_id = nullif(current_setting('app.clan_id', true), '')::uuid"

_SELECT_POLICY = "user_clan_roles_sel"
_INSERT_POLICY = "user_clan_roles_ins"
_UPDATE_POLICY = "user_clan_roles_upd"
_DELETE_POLICY = "user_clan_roles_del"
_ALL_POLICIES = (_SELECT_POLICY, _INSERT_POLICY, _UPDATE_POLICY, _DELETE_POLICY)


def upgrade() -> None:
    op.execute("ALTER TABLE user_clan_roles ENABLE ROW LEVEL SECURITY")
    for policy in _ALL_POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON user_clan_roles")

    # Permissive by decision, not by oversight — see the module docstring. Every
    # clan-less reader of this table is cross-clan by design, starting with the
    # authorization gate itself.
    op.execute(f"CREATE POLICY {_SELECT_POLICY} ON user_clan_roles FOR SELECT USING (true)")
    # Permissive for the same reason: POST /auth/onboard writes the caller's own
    # membership with no clan selected, and on the create branch the clan does not
    # exist until that request makes it.
    op.execute(f"CREATE POLICY {_INSERT_POLICY} ON user_clan_roles FOR INSERT WITH CHECK (true)")
    # The two halves this migration exists for. USING decides which row the command may
    # reach; WITH CHECK stops an UPDATE moving a row into another clan.
    op.execute(
        f"CREATE POLICY {_UPDATE_POLICY} ON user_clan_roles FOR UPDATE "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute(f"CREATE POLICY {_DELETE_POLICY} ON user_clan_roles FOR DELETE USING ({_PREDICATE})")


def downgrade() -> None:
    for policy in reversed(_ALL_POLICIES):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON user_clan_roles")
    op.execute("ALTER TABLE user_clan_roles DISABLE ROW LEVEL SECURITY")
