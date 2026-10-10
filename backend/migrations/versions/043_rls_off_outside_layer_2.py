"""The four tables the chain leaves outside layer 2 have RLS off on Supabase too (#261).

ADR-066, amended 2026-10-10. The hosted Supabase project ships an event trigger,
``ensure_rls`` (``ddl_command_end``, function ``public.rls_auto_enable``, SECURITY DEFINER,
owned by ``supabase_admin``). On every ``CREATE TABLE`` in ``public`` it runs
``alter table … enable row level security``. So on that project every table this chain
creates gets RLS, including the four it deliberately leaves without RLS:

- ``alembic_version``, which Alembic itself creates on the first ``upgrade``;
- ``clans``, which the auth path reads before any clan is selected;
- ``user_profiles`` and ``user_fcm_tokens``, which ADR-059 keeps outside layer 2.

None of the four has a policy, so on Supabase the request role ``familyroots_app``, which
neither owns them nor bypasses RLS, saw no row in any of them and could write none.
Read on the hosted project on 2026-10-10: ``relrowsecurity`` true and zero policies on
all four. ``/health`` runs on the request session, so it found no ``alembic_version`` row
and answered ``migrations: behind`` while the database was at head. The lifespan gate read
on the owner session and passed, so the API booted. Login and every clan screen read
``user_profiles`` or ``clans`` on the same session.

``upgrade`` turns RLS off on the four. Where it is already off, as in CI, compose and plain
Postgres, ``DISABLE ROW LEVEL SECURITY`` changes nothing. The login owns all four, which is
the privilege the statement needs. With 042's revokes, the grants are what keep the Data
API's roles out of these tables, as ADR-059 § 5 required.

**What it does not do.** It does not drop or disable ``ensure_rls``. The login does not own
that trigger, and it is the project's own default. Every later table the chain creates in
``public`` will therefore arrive with RLS on, on Supabase only. A table meant to stay
outside layer 2 must turn RLS off in its own migration.
``tests/integration/test_supabase_shaped_database.py`` installs the same trigger and fails,
naming the table, when any table's RLS state there differs from plain Postgres.

``downgrade`` is a deliberate no-op. The state before this revision differs by environment:
RLS was on for these four on Supabase and off everywhere else. Turning it back on would
break the request role on Supabase again and invent a state plain Postgres never had.

Revision ID: 043_rls_off_outside_layer_2
Revises: 042_close_data_api_on_public
"""

from __future__ import annotations

from alembic import op

revision: str = "043_rls_off_outside_layer_2"
down_revision: str | None = "042_close_data_api_on_public"
branch_labels: str | None = None
depends_on: str | None = None

# Each table here is one this chain creates without RLS and never enables it on.
_OUTSIDE_LAYER_2 = ("alembic_version", "clans", "user_profiles", "user_fcm_tokens")


def upgrade() -> None:
    for table in _OUTSIDE_LAYER_2:
        op.execute(f"ALTER TABLE IF EXISTS public.{table} DISABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Deliberately empty. See the module docstring.
    pass
