#!/usr/bin/env python3
"""Bootstrap the platform super admin account.

The super admin, like every user, exists in **two databases at once**, and this script
writes each half where it lives (docs/ops/local-supabase.md § "The topology"):

* the **identity** in the Supabase project's ``auth.users``, through the GoTrue admin API, and
* the **profile row**, ``platform_role = 'super_admin'``, in the application database named
  by ``DATABASE_URL``. ``get_super_admin`` reads that row and nothing else.

Until issue #168 the profile row was written, and the "already exists" check read, through
the Supabase Data API, which fronts a database that holds no ``user_profiles`` table.

Run once during initial platform setup (from ``backend/``, which owns the virtualenv)::

    cd backend
    uv run python ../scripts/bootstrap_super_admin.py

Environment:

    DATABASE_URL                the application database. SQLAlchemy-style ``+driver``
                                suffixes are stripped before libpq sees it.
    SUPABASE_URL                the Supabase project URL.
    SUPABASE_SERVICE_ROLE_KEY   the Supabase service role key.

Refuses if the application database already holds a super admin.
"""

import getpass
import os
import re
import sys
from collections.abc import Callable
from typing import Any

import psycopg
from supabase import create_client

SQL_SUPER_ADMIN_EXISTS = """
SELECT EXISTS (SELECT 1 FROM user_profiles WHERE platform_role = 'super_admin')
"""

# language, timezone, is_active and both timestamps take their server defaults
# (migrations/versions/001_initial.py).
SQL_INSERT_SUPER_ADMIN = """
INSERT INTO user_profiles (id, email, display_name, platform_role)
VALUES (%(id)s, %(email)s, 'Super Admin', 'super_admin')
"""


class Refused(Exception):
    """A reason to stop, printed as the script's last line."""


def _require_env(name: str, hint: str = "") -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise Refused(f"{name} must be set. {hint}".rstrip())
    return value


def app_dsn() -> str:
    """The application database DSN, with any SQLAlchemy ``+driver`` suffix removed."""
    raw = _require_env(
        "DATABASE_URL",
        "It is the application database that Alembic migrates, not the Supabase database.",
    )
    return re.sub(r"^(postgresql|postgres)\+[a-z0-9_]+://", r"\1://", raw)


def super_admin_exists(conn: psycopg.Connection[Any]) -> bool:
    try:
        row = conn.execute(SQL_SUPER_ADMIN_EXISTS).fetchone()
    except psycopg.errors.UndefinedTable as exc:
        raise Refused(
            "DATABASE_URL names a database with no user_profiles table. It must be the "
            "application database that Alembic migrates (pgdb, port 5432 locally), not the "
            "Supabase database."
        ) from exc
    return bool(row and row[0])


def bootstrap(
    conn: psycopg.Connection[Any],
    create_identity: Callable[[str, str], str],
    read_credentials: Callable[[], tuple[str, str]],
) -> str:
    """Create the single super admin and return its email.

    The check runs before anything is asked or created, so a refused run leaves no
    orphaned identity in ``auth.users``.
    """
    if super_admin_exists(conn):
        raise Refused("A super admin already exists. This script can only be run once.")

    email, password = read_credentials()
    user_id = create_identity(email, password)
    conn.execute(SQL_INSERT_SUPER_ADMIN, {"id": user_id, "email": email})
    conn.commit()
    return email


def prompt_credentials() -> tuple[str, str]:
    email = input("Super admin email: ").strip()
    if not email:
        raise Refused("Email is required.")

    password = getpass.getpass("Super admin password (min 12 chars): ")
    if len(password) < 12:
        raise Refused("Password must be at least 12 characters.")
    return email, password


def supabase_identity_creator(
    supabase_url: str, service_role_key: str
) -> Callable[[str, str], str]:
    """Create a confirmed identity through the GoTrue admin API and return its id."""
    admin = create_client(supabase_url, service_role_key).auth.admin

    def create(email: str, password: str) -> str:
        response = admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"platform_role": "super_admin"},
            }
        )
        return str(response.user.id)

    return create


def main() -> int:
    try:
        dsn = app_dsn()
        create_identity = supabase_identity_creator(
            _require_env("SUPABASE_URL"), _require_env("SUPABASE_SERVICE_ROLE_KEY")
        )
        with psycopg.connect(dsn) as conn:
            email = bootstrap(conn, create_identity, prompt_credentials)
    except Refused as exc:
        print(f"❌ {exc}")
        return 1
    except psycopg.OperationalError as exc:
        print(f"❌ Cannot reach the application database named by DATABASE_URL: {exc}")
        return 1

    print(f"✅ Super admin created: {email}")
    print("⚠️  Store these credentials securely. This script cannot be run again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
