"""The migrating login may enter the request role: ``SET`` on ``familyroots_app`` (#251).

ADR-066. Migration 002 creates ``familyroots_app NOLOGIN`` and no migration grants it to
anyone. On a superuser login that never mattered, because a superuser may ``SET ROLE`` to
any role. Supabase's ``postgres`` is not a superuser. It holds ``CREATEROLE``, and since
Postgres 16 the non-superuser creator of a role receives an implicit grant of it
``WITH ADMIN TRUE, INHERIT FALSE, SET FALSE`` while ``createrole_self_grant`` is empty,
which is its default and what the local Supabase stack runs. ADMIN lets the creator grant
the role. It does not let the creator become it. So the ``SET LOCAL ROLE familyroots_app``
that ``app/core/rls.py`` issues at the start of every request transaction fails with
``permission denied to set role "familyroots_app"``, the production boot gate in
``app/main.py`` refuses to start, and RLS layer 2 never runs. Read on Postgres 17.11 on
2026-10-10, and recorded on issue #251.

``upgrade`` first asks the server whether the login can already enter the role, with
``pg_has_role(current_user, 'familyroots_app', 'SET')``. A superuser can, and so can a
login that holds SET some other way. For those it does nothing. Otherwise it grants the
role to the login itself, ``WITH INHERIT FALSE, SET TRUE``, using the ADMIN option the
creator holds, so the grantor on record is the login. INHERIT is false because the login
needs to become the role, not to carry its privileges: it already owns every table. A
login that can neither enter the role nor grant it fails the upgrade and is named,
rather than leaving a database the application cannot open.

``downgrade`` revokes only the grant ``upgrade`` makes. That is the row whose member and
grantor are both the login, with SET, without INHERIT, and without ADMIN. It never
touches the creator's ADMIN grant, which names the bootstrap superuser as grantor, or a
grant any other role made, or a self-grant with other options.

**Role membership is a cluster object, not a database object.** Two databases in one
cluster, migrated by the same non-superuser login, share this grant. The second one's
``upgrade`` finds SET already held and does nothing, and downgrading the first revokes it
for both. That is the same sharing ``002``'s downgrade names for the role itself.

**Every role is named, never written as ``CURRENT_USER``.** Supabase's ``supautils``
hook crashes the backend with signal 11 on ``GRANT <role> TO CURRENT_USER`` and on
``REVOKE <role> FROM CURRENT_USER``. Postgres then restarts every process in the cluster.
Measured 2026-10-10 on ``supabase/postgres:17.6.1.084``: the first version of this file did
that to the local stack, and a private container of the same image reproduced it with
each statement alone, while the same statements with the login's name ran cleanly. Plain
Postgres accepts both forms, so CI cannot see this. The names go through ``format('%I')``.

Needs Postgres 16 or later, for ``pg_has_role(..., 'SET')`` and ``GRANT ... WITH SET``.
``docs/architecture/data-model.md`` names 16 as the floor. CI and compose run 18, and the
Supabase project runs 17.

Pinned by ``tests/integration/test_supabase_shaped_database.py``.

Revision ID: 041_grant_app_role_to_login
Revises: 040_clan_slug_one_shape
"""

from __future__ import annotations

from alembic import op

revision: str = "041_grant_app_role_to_login"
down_revision: str | None = "040_clan_slug_one_shape"
branch_labels = None
depends_on = None

_ROLE = "familyroots_app"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF pg_has_role(current_user, '{_ROLE}', 'SET') THEN
                RETURN;
            END IF;
            IF NOT pg_has_role(current_user, '{_ROLE}', 'MEMBER WITH ADMIN OPTION') THEN
                RAISE EXCEPTION
                    'login % can neither SET ROLE {_ROLE} nor grant it (#251, ADR-066)',
                    current_user
                    USING HINT = 'Run the migrations as the role that created {_ROLE}, '
                                 'or have a superuser run: GRANT {_ROLE} TO '
                                 || quote_ident(current_user) || ' WITH SET TRUE';
            END IF;
            EXECUTE format(
                'GRANT %I TO %I WITH INHERIT FALSE, SET TRUE GRANTED BY %I',
                '{_ROLE}', current_user, current_user
            );
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_auth_members a
                JOIN pg_roles r ON r.oid = a.roleid
                JOIN pg_roles m ON m.oid = a.member
                WHERE r.rolname = '{_ROLE}'
                  AND m.rolname = current_user
                  AND a.grantor = a.member
                  AND a.set_option
                  AND NOT a.inherit_option
                  AND NOT a.admin_option
            ) THEN
                EXECUTE format(
                    'REVOKE %I FROM %I GRANTED BY %I', '{_ROLE}', current_user, current_user
                );
            END IF;
        END
        $$;
        """
    )
