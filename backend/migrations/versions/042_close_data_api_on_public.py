"""The Supabase Data API's roles hold nothing in ``public`` (#251).

ADR-066. With the application database inside the Supabase project, PostgREST serves
every schema the project exposes, ``public`` by default, to anyone holding the anon key,
and that key ships in the web bundle. PostgREST enters ``anon`` for a request with no
session and ``authenticated`` for one with a session, so those two roles' privileges are
the whole of what the Data API can do. Two things would hand them the application's
tables:

- **Supabase's default privileges.** The legacy default, which ``supabase/config.toml``
  calls ``auto_expose_new_tables``, grants both roles ALL on every table, sequence and
  function ``postgres`` creates in ``public``. The local stack's image
  (``supabase/postgres:17.6.1.084``, read 2026-10-10) grants TRUNCATE, REFERENCES,
  TRIGGER and MAINTAIN on tables, plus UPDATE on sequences, and no SELECT or INSERT. The
  hosted project was not read. This revision is written for the worst of those.
- **Our own policies, which name no role.** Every ``CREATE POLICY`` in this chain applies
  to ``PUBLIC``, so it applies to ``anon`` too. Clan-keyed policies fail closed, because
  nothing on the Data API path sets ``app.clan_id``. Three policies are permissive by
  decision and read no GUC: ``user_clan_roles_sel USING (true)`` and
  ``user_clan_roles_ins WITH CHECK (true)`` (036, ADR-050), and
  ``audit_logs_ins WITH CHECK (true)`` (034, ADR-043). ``user_profiles`` and
  ``user_fcm_tokens`` have no RLS at all (ADR-059). With a table grant, the Data API
  could read every user's email, and could insert an approved admin row into
  ``user_clan_roles`` for any clan.

So for each of ``anon`` and ``authenticated`` that exists, ``upgrade``:

1. revokes ALL on every table, sequence and routine in ``public``;
2. revokes ALL from the login's default privileges in ``public``, so a later migration's
   table is not granted to either role on creation;
3. does the same to the login's global default privileges, the form without
   ``IN SCHEMA``. Postgres adds per-schema defaults to global ones, and a per-schema
   REVOKE cannot remove a privilege that a global default grants.

Where neither role exists, as in CI, compose and plain Postgres, it does nothing.

**What it does not do.** It leaves ``service_role``, which only the backend holds, and
``USAGE`` on the schema. It does not touch ``PUBLIC``'s EXECUTE on functions, which
Postgres grants by default and which ``anon`` inherits as everyone does. Every routine in
``public`` is ``SECURITY INVOKER``, so a call through ``/rpc`` reads its tables as
``anon`` and is refused at the first one. It can only change default privileges for the
login it runs as. Objects ``supabase_admin`` creates in ``public`` keep that role's own
defaults. Removing ``public`` from the Data API's exposed schemas is the second lock,
and that is a dashboard step recorded in ADR-066, not something SQL can do.

``downgrade`` is a deliberate no-op. A rollback should never re-open the Data API onto
the application's tables, and the grants it would restore were never the application's.

Pinned by ``tests/integration/test_supabase_shaped_database.py``.

Revision ID: 042_close_data_api_on_public
Revises: 041_grant_app_role_to_login
"""

from __future__ import annotations

from alembic import op

revision: str = "042_close_data_api_on_public"
down_revision: str | None = "041_grant_app_role_to_login"
branch_labels = None
depends_on = None

# The two roles PostgREST switches into for a request. The names are Supabase's, and
# copied rather than configured: a migration must keep meaning what it meant when it ran.
_DATA_API_ROLES = ("anon", "authenticated")


def upgrade() -> None:
    roles = ", ".join(f"'{role}'" for role in _DATA_API_ROLES)
    op.execute(
        f"""
        DO $$
        DECLARE
            r text;
        BEGIN
            FOREACH r IN ARRAY ARRAY[{roles}] LOOP
                CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r);

                EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', r);
                EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', r);
                EXECUTE format('REVOKE ALL ON ALL ROUTINES IN SCHEMA public FROM %I', r);

                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', r);
                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', r);
                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON ROUTINES FROM %I', r);

                EXECUTE format('ALTER DEFAULT PRIVILEGES REVOKE ALL ON TABLES FROM %I', r);
                EXECUTE format('ALTER DEFAULT PRIVILEGES REVOKE ALL ON SEQUENCES FROM %I', r);
                EXECUTE format('ALTER DEFAULT PRIVILEGES REVOKE ALL ON ROUTINES FROM %I', r);
            END LOOP;
        END
        $$;
        """
    )


def downgrade() -> None:
    # Deliberately empty. See the module docstring: a rollback does not re-grant the Data
    # API's roles anything in ``public``.
    pass
