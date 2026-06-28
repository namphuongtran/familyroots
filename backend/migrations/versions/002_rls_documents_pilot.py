"""RLS defense-in-depth pilot: familyroots_app role + clan policy on documents.

ADR-008. This is the documents-first pilot. It creates a dedicated
non-privileged role (``familyroots_app``, NOBYPASSRLS by default) and enables
Row-Level Security on ``documents`` with a clan-isolation policy driven by the
``app.clan_id`` GUC.

Safety: RLS is ``ENABLE``d (not ``FORCE``d), so it applies to the non-owner
``familyroots_app`` role but the privileged owner/superuser connection the app
currently uses still bypasses it — the running app is unaffected until it is
deliberately switched to the ``familyroots_app`` role (a later activation step).
The role is cluster-global; its creation is idempotent (re-runnable). The policy
is dropped-if-exists before creation so the upgrade body is itself re-runnable.

Revision ID: 002_rls_documents_pilot
Revises: 001_initial
"""

from __future__ import annotations

from alembic import op

revision: str = "002_rls_documents_pilot"
down_revision: str | None = "001_initial"
branch_labels = None
depends_on = None

_ROLE = "familyroots_app"


def upgrade() -> None:
    # 1. Dedicated non-privileged request role (NOBYPASSRLS is the default).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROLE}') THEN
                CREATE ROLE {_ROLE} NOLOGIN;
            END IF;
        END
        $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {_ROLE}")
    # Future tables created by the migration owner are auto-granted to the role.
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {_ROLE}"
    )

    # 2. Enable RLS + clan-isolation policy on the pilot table.
    # Contract for the app.clan_id GUC: a valid UUID string (the active clan) or
    # empty/unset. nullif(..., '')::uuid yields NULL when unset/empty, so the
    # equality is NULL and the policy denies all rows (fail-closed default-deny).
    # A non-empty, non-UUID value raises invalid-uuid-syntax (safe: aborts the
    # statement, never leaks) — the app always sets a validated UUID.
    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS documents_clan_isolation ON documents")
    op.execute(
        """
        CREATE POLICY documents_clan_isolation ON documents
            USING (clan_id = nullif(current_setting('app.clan_id', true), '')::uuid)
            WITH CHECK (clan_id = nullif(current_setting('app.clan_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS documents_clan_isolation ON documents")
    op.execute("ALTER TABLE documents DISABLE ROW LEVEL SECURITY")
    # The role + default privileges are cluster-global and may be shared; leave
    # them in place (idempotent re-create on upgrade). Drop manually if needed:
    #   ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ... ; DROP OWNED BY familyroots_app; DROP ROLE familyroots_app;
