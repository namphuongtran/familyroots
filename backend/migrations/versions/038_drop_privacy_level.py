"""Drop ``clan_settings.privacy_level`` (S-018, ADR-044 § 2).

**Dropping this column is not a decision against per-clan privacy.** It is a refusal to
carry a control that restricts nothing. A ``privacy_level`` column that exists is the field
a later screen renders, and a switch labelled *riêng tư* that changes no read is the most
dangerous control in this product: the trưởng họ believes the tree is private and it is
not. The design spec fixes that rule at
``docs/superpowers/specs/2026-08-02-design-system-and-screens.md:2400-2402``.

**The concept may return; this shape may not.** ADR-044 § 2 names the four terms it returns
on, in one change: a value domain closed at the database (``NOT NULL``, a default, and a
``CHECK`` or an enum), ``get_current_clan_id`` plus ``RequireViewer`` as the enforcement
point, a failure direction where a missing row, a NULL or an unrecognized value all resolve
to the **most restrictive** value the domain holds, and a row creator built first. Today's
column has none of those. It is a bare ``String(20)`` with no constraint anywhere
(``grep -rn "privacy_level" backend/migrations`` returns only column definitions), so an
unrecognized value is a value, and a reader branching on it falls through to its permissive
arm — the failure direction the design rule forbids.

**The drop loses nothing, which is why this is a migration and not a deprecation.**
``clan_settings`` has no rows: nothing constructs a ``ClanSettings``, ``001_initial.py``
installs no trigger that would create one (its only triggers are ``trg_<table>_updated_at``,
``001_initial.py:930-937``), and no code reads the column. Measured by S-010, by S-016
(ADR-044 Measurement 3), and re-measured on 2026-08-22 by this seed over the **whole**
tracked tree rather than ``backend/app web/src mobile/lib`` — the narrower root is the
scope defect S-017 amended into ADR-044 Measurement 1. ``git grep -n "privacy_level"``
returned no hit under ``backend/tests``: unlike ``allow_public_tree``, this column was never
even an arbitrary test payload.

So the round trip is exact rather than lossy. ``downgrade()`` re-adds the column with the
**same** ``NOT NULL`` and the **same** ``server_default 'clan_members'`` that
``001_initial.py:603`` gave it, and with no rows there is no per-row value to reconstruct.
Compare ``014_drop_date_approx``, which could not say that: its downgrade lands every row on
``false`` regardless of the prior value.

Nothing else changes. The RLS policy from ``035_rls_clan_settings`` is untouched — ADR-044
§ 4 says why a policy is not the enforcement point for privacy, and the policy keys on
``clan_id``, never on this column — and no API request or response shape moves, because no
contract ever documented the column.

Revision ID: 038_drop_privacy_level
Revises: 037_drop_allow_public_tree
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "038_drop_privacy_level"
down_revision: str | None = "037_drop_allow_public_tree"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("clan_settings", "privacy_level")


def downgrade() -> None:
    op.add_column(
        "clan_settings",
        sa.Column(
            "privacy_level",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'clan_members'"),
        ),
    )
