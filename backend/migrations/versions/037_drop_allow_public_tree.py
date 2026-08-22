"""Drop ``clan_settings.allow_public_tree`` (S-017, ADR-044 § 1).

**This column may not come back.** The *concept* of a public tree may, one day, but it
returns as ``privacy_level`` and not as a boolean beside it. ADR-044 § 1: ``privacy_level
= 'public'`` and ``allow_public_tree = true`` are the same fact, and two authorities on one
question is the defect ADR-027 exists to prevent. ``privacy_level`` can express this
boolean completely; the reverse is false, so the boolean is the redundant one.

**The drop loses nothing, which is why this is a migration and not a deprecation.**
``clan_settings`` has no rows: nothing constructs a ``ClanSettings``, ``001_initial.py``
installs no trigger that would create one (its only triggers are ``trg_<table>_updated_at``,
``001_initial.py:930-937``), and no code reads the column. Measured by S-010, by S-016
(ADR-044 Measurement 3), and re-measured on 2026-08-22 by this seed:
``grep -rn "allow_public_tree" backend/app web/src mobile/lib`` returned exactly one line,
the ORM declaration this change removes.

So the round trip is exact rather than lossy. ``downgrade()`` re-adds the column with the
**same** ``NOT NULL`` and the **same** ``server_default false`` that ``001_initial.py:600``
gave it, and with no rows there is no per-row value to reconstruct. Compare
``014_drop_date_approx``, which could not say that: its downgrade lands every row on
``false`` regardless of the prior value.

Nothing else changes. The RLS policy from ``035_rls_clan_settings`` is untouched — ADR-044
§ 4 says why a policy is not the enforcement point for privacy — and no API request or
response shape moves, because no contract ever documented this column.

Revision ID: 037_drop_allow_public_tree
Revises: 036_rls_user_clan_roles
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "037_drop_allow_public_tree"
down_revision: str | None = "036_rls_user_clan_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("clan_settings", "allow_public_tree")


def downgrade() -> None:
    op.add_column(
        "clan_settings",
        sa.Column(
            "allow_public_tree",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
