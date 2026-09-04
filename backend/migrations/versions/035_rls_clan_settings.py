"""RLS layer-2 Phase 10: clan_settings takes the 027 template. user_clan_roles does NOT.

Phase 10 named two tables. Only one of them ships here, and the other half became a
decision seed. This docstring is the durable record of why, because the seed tracker is
not what the next agent reads when it opens a migration.

``clan_settings`` — the migration-027 template, unchanged
---------------------------------------------------------
``clan_id`` is NOT NULL and UNIQUE (``app/models/clan_settings.py:17-21``,
``001_initial.py:580``), one row per clan, so there is no row the predicate mishandles and
no NULL branch to reason about. Both halves are clan-keyed: ``USING`` for reads,
``WITH CHECK`` for writes.

**The policy is INERT on 2026-08-22, and that is stated rather than left to be discovered.**
Measured on 2026-08-22 by ``grep -rn 'clan_settings\\|ClanSettings' backend/app``: the only
application reference to the table outside the ORM model itself is the ``Clan.settings``
relationship at ``app/models/clan.py:35``. Nothing reads ``clan.settings``, nothing
constructs a ``ClanSettings``, no route, repository or query port touches the table, and
``001_initial.py`` installs no trigger that would populate it — the only triggers it creates
are ``trg_<table>_updated_at`` (``001_initial.py:930-937``). So the table is empty and
unread today. ``docs/architecture/data-model.md`` said "Auto-created with new clans", which
is false; it is corrected in the same commit as this migration.

This is the ``notification_log`` situation from ADR-043 § 2 repeating: a cheap correct policy
that guards a reader which does not exist yet, taken over a permanent exemption row in
the clan-owned table list, on the grounds that a second place to record a fact is a
second place to be wrong.

**One live read path does exist, and it is the one that had to be checked before shipping.**
``Clan.settings`` is declared ``lazy="selectin"`` (``app/models/clan.py:35``), so every load
of a ``Clan`` ORM entity emits a second SELECT against ``clan_settings``. Two of those loads
run on the RLS request session with **no clan GUC set**: ``get_clan_by_slug``
(``app/infrastructure/persistence/auth_repository.py:47-49``) and ``get_clan_by_id``
(``:51-52``), both reached from ``POST /auth/register`` and ``POST /auth/onboard`` through
``get_auth_command_handler``, which is wired to ``get_db``
(``app/infrastructure/dependencies.py:192-202``). Under this policy that selectin returns
zero rows and ``clan.settings`` is ``None``. Measured 2026-08-22: both onboard flows still
answer ``201`` with this policy live, because nothing consumes ``clan.settings``. Pinned by
``tests/integration/test_rls_phase10_clan_settings.py``, which drives both onboard flows over
the real seam rather than asserting the absence in prose — the day something starts reading
``clan.settings`` on a clan-less path, that test is what fails.

That selectin fan-out is also the reason this addition is low-risk rather than merely
believed to be. ``Clan`` declares FIVE ``lazy="selectin"`` relationships
(``app/models/clan.py:32-36``): ``origin_persons``, ``clan_memberships``, ``user_roles``,
``settings`` and ``branches``. Three of those targets — ``persons`` (migration 029),
``clan_memberships`` (031) and ``branches`` (027) — have carried clan policies since before
this seed, so the clan-less auth path has already been loading a ``Clan`` whose eager
collections come back empty, every day, with every gate green. ``clan_settings`` joins a
pattern that is already load-bearing, not a new one.

``user_clan_roles`` — deliberately NOT included, and it cannot be until a decision is made
-------------------------------------------------------------------------------------------
This is the same shape as migration ``031``'s exclusion of ``clan_invitations``, which became
ADR-048. It is sharper here: ``user_clan_roles`` is the table the authorization gate reads,
so a policy that hides a role row does not merely hide data, it silently downgrades what the
caller may do.

Re-measured 2026-08-22 by adding ``user_clan_roles`` to this migration's table list and
running the suite. It breaks in **both** directions:

* **Reads fail silently.** ``get_current_clan_id`` queries the table on the request session
  at ``app/core/security.py:249-254`` and only sets ``app.clan_id`` afterwards at ``:290``,
  so the predicate is NULL for its own read. ``SqlAlchemyAuthQueryPort.get_login_profile``
  (``auth_repository.py:120-137``) and ``SqlAlchemyMeQueryPort.list_clans``
  (``me_query_port.py:19-42``) read it before any clan exists to select.
  ``POST /auth/login`` still answers ``200`` with ``clan_id: None`` and ``GET /me/clans``
  returns ``[]``. Nothing raises and nothing is logged.
* **Writes fail loudly, which the seed did not record.**
  ``SqlAlchemyAuthRepository.add_membership`` (``auth_repository.py:69-88``) INSERTs the row
  on that same clan-less request session, so a clan-keyed ``WITH CHECK`` compares
  ``<real clan> = NULL``. Measured on both onboard flows:
  ``psycopg.errors.InsufficientPrivilege: new row violates row-level security policy for
  table "user_clan_roles"``, surfacing as a 500.

Choosing between "move the clan-resolution reads to the privileged session", "set the GUC
before they run", and "keep RLS off this table" changes the isolation posture of the
authorization gate itself, so it is a decision with its own ADR rather than part of this
migration. The read half is pinned by
``tests/integration/test_rls_login_two_clans.py``; the write half was added to that same file
by this seed.

``ENABLE``, not ``FORCE``: the system session connects as a bypassing role. Grants already
exist (migration 002 table CRUD + 026 functions). Reversible (drop policy + disable).

Revision ID: 035_rls_clan_settings
Revises: 034_rls_audit_notification
"""

from __future__ import annotations

from alembic import op

revision: str = "035_rls_clan_settings"
down_revision: str | None = "034_rls_audit_notification"
branch_labels = None
depends_on = None

_TABLES = ("clan_settings",)
# The migration-027 predicate, verbatim. An unset GUC → empty string → nullif → NULL →
# no row matches and no write is admitted (fail closed).
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
