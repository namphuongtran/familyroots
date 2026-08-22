-- Restore bootstrap: the cluster-wide familyroots_app role and its schema grants.
--
-- ADR-052 (docs/decisions/052-restore-bootstraps-the-request-role.md).
-- Run as a superuser, against the RESTORED DATABASE, AFTER pg_restore:
--
--   psql "$RESTORE_DSN" -v ON_ERROR_STOP=1 -f scripts/restore_bootstrap_role.sql
--
-- Why this file exists. A Postgres role is a cluster object, and a GRANT is a
-- database object. `pg_dump` of one database carries neither: scripts/db_backup.sh
-- passes --no-owner --no-privileges, so a dump restored into a cluster that never
-- held familyroots_app produces a database with the role absent and 0 grant rows.
-- RLS is still enabled on that database, and the request path issues
-- `SET LOCAL ROLE familyroots_app` on every transaction
-- (backend/app/core/rls.py:63, settings.RLS_ENABLED defaults True at
-- backend/app/core/config.py:71). The restored database is armed but unusable.
-- Measured 2026-08-22 by seed S-050; see docs/ops/backup-restore.md.
--
-- These statements are the ones the migration chain already runs. They are copied
-- from, and must stay equal to:
--   backend/migrations/versions/002_rls_documents_pilot.py:33-50 (role at :38, grants at :44-50)
--   backend/migrations/versions/026_rls_activation_grants.py:30-37 (four statements)
-- **Any migration that changes what familyroots_app may do must change this file in
-- the same pull request.** Nothing enforces that mechanically. What does catch a
-- missing SELECT/INSERT/UPDATE/DELETE or EXECUTE grant is the request-role check in
-- scripts/restore_drill.sh, which runs a real query as the role after this file.
--
-- Every statement is idempotent, so running the file twice, or running it against a
-- cluster that already holds the role, changes nothing.
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
