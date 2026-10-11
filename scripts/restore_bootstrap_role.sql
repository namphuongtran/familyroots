-- Restore bootstrap: the cluster-wide familyroots_app role, its grants, and what else the
-- migration chain did that a dump does not carry.
--
-- ADR-052 (docs/decisions/052-restore-bootstraps-the-request-role.md), amended for #283.
-- Run against the RESTORED DATABASE, AFTER pg_restore:
--
--   psql "$RESTORE_DSN" -v ON_ERROR_STOP=1 -f scripts/restore_bootstrap_role.sql
--
-- Which login may run it. On plain Postgres, a superuser, which is what
-- scripts/restore_drill.sh uses. On a Supabase project, which offers no superuser, the
-- login the application and the migrations use, `postgres`: it holds CREATEROLE, and
-- ADMIN on familyroots_app as the role's creator. Run it as the same login that ran
-- pg_restore, because section 5 can only change that login's default privileges and
-- section 4 grants the role to that login.
--
-- Why this file exists. A Postgres role is a cluster object, and a GRANT is a
-- database object. `pg_dump` of one database carries neither: scripts/db_backup.sh
-- passes --no-owner --no-privileges, so a dump restored into a cluster that never
-- held familyroots_app produces a database with the role absent and 0 grant rows.
-- RLS is still enabled on that database, and the request path issues
-- `SET LOCAL ROLE familyroots_app` on every transaction
-- (backend/app/core/rls.py:63, settings.RLS_ENABLED defaults True at
-- backend/app/core/config.py:71). The restored database is armed but unusable.
-- Measured 2026-08-22 by the restore drill; see docs/ops/backup-restore.md.
-- The restored alembic_version already reads head, so no migration runs again, and
-- whatever a migration did outside the dump has to be done here.
--
-- These statements are the ones the migration chain already runs. They are copied
-- from, and must stay equal to:
--   backend/migrations/versions/002_rls_documents_pilot.py:33-50 (role at :38, grants at :44-50)
--   backend/migrations/versions/026_rls_activation_grants.py:30-37 (four statements)
--   backend/migrations/versions/041_grant_app_role_to_login.py:64-87 (the login's SET membership)
--   backend/migrations/versions/042_close_data_api_on_public.py:69-98 (the Data API revokes)
--   backend/migrations/versions/043_rls_off_outside_layer_2.py:51-56 (RLS off on four tables)
-- **Any migration that changes what familyroots_app may do, what the Data API's roles
-- may do, or which tables run without RLS, must change this file in the same pull
-- request.** Nothing enforces that mechanically. What catches a gap is a reading, not a
-- comparison: the request-role check in scripts/restore_drill.sh, which runs a real
-- query as the role after this file on plain Postgres, and
-- backend/tests/integration/test_restore_bootstrap_on_supabase_shape.py, which restores
-- the chain into a Supabase-shaped database as its login and reads what each role can do.
--
-- Every statement is idempotent, so running the file twice, or running it against a
-- cluster that already holds the role, changes nothing. Sections 4 to 6 are no-ops on
-- plain Postgres run as a superuser: a superuser may already SET ROLE, no anon or
-- authenticated role exists there, and RLS is already off on the four tables.
--
-- The role name is spelled out rather than parameterised, because migrations 002 and
-- 026 spell it out too. settings.RLS_APP_ROLE (backend/app/core/config.py:72) is
-- therefore only settable to familyroots_app in practice.

-- 1. The cluster-wide role. NOBYPASSRLS is the default, which is the point of it.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'familyroots_app') THEN
        CREATE ROLE familyroots_app NOLOGIN;
    END IF;
END
$$;

-- 2. Schema + table grants (migration 002).
GRANT USAGE ON SCHEMA public TO familyroots_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO familyroots_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO familyroots_app;

-- 3. Function + sequence grants (migration 026).
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO familyroots_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO familyroots_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO familyroots_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO familyroots_app;

-- 4. The login may enter the role (migration 041). A non-superuser creator holds ADMIN
-- on the role without SET, so `SET LOCAL ROLE familyroots_app` fails until this grant
-- exists. The login is named through format('%I'), never written as CURRENT_USER:
-- Supabase's supautils hook crashes the backend on `GRANT <role> TO CURRENT_USER`.
DO $$
BEGIN
    IF pg_has_role(current_user, 'familyroots_app', 'SET') THEN
        RETURN;
    END IF;
    IF NOT pg_has_role(current_user, 'familyroots_app', 'MEMBER WITH ADMIN OPTION') THEN
        RAISE EXCEPTION
            'login % can neither SET ROLE familyroots_app nor grant it (#283, ADR-052)',
            current_user
            USING HINT = 'Run this file as the login that created familyroots_app. '
                         'docs/ops/backup-restore.md, "Restoring for real", says which.';
    END IF;
    EXECUTE format(
        'GRANT %I TO %I WITH INHERIT FALSE, SET TRUE GRANTED BY %I',
        'familyroots_app', current_user, current_user
    );
END
$$;

-- 5. The Data API's roles hold nothing in public (migration 042). pg_restore created
-- every table as this login, so the login's default privileges granted them whatever
-- Supabase's defaults grant, ALL at worst. Skipped where neither role exists.
DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
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

-- 6. RLS off on the four tables the chain leaves outside layer 2 (migration 043). A
-- Supabase project's ensure_rls event trigger turns RLS on for every table pg_restore
-- creates, and none of these four has a policy, so the request role would read no row.
-- Every other table keeps the RLS state the dump carried.
ALTER TABLE IF EXISTS public.alembic_version DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.clans DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.user_profiles DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.user_fcm_tokens DISABLE ROW LEVEL SECURITY;
