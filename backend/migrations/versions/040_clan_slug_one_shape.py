"""``clans.slug`` takes the one shape the API already admits (#190).

Before this revision two rules described the clan code, and they disagreed both ways.
``ck_clans_clans_slug_format`` from ``001_initial.py:56`` (the naming convention in
``app/models/base.py:16`` doubles the table name) was
``slug ~ '^[a-z0-9][a-z0-9\\-]*[a-z0-9]$'``: it refused a one-character code the API
admitted, and admitted a doubled hyphen the API refused. The shape adopted is the
intersection, so each layer takes the other's stricter half. The API took the CHECK's
two-character minimum (``_ClanCode`` in ``app/schemas/auth.py``). This revision gives
the CHECK the API's single-hyphen rule, by reusing ``_SLUG_PATTERN`` verbatim, as
ADR-057 section 2 requires, beside the same minimum.

Forward-compatible with the running app (``docs/ops/migrations.md``): no request the app
can send today stops working. The app already refuses ``--`` at the door, and a
one-character code already failed, as a 500 on create and a 404 on join.

**``upgrade`` rewrites no slug.** A slug is the code people type to join and the
identifier in links already sent, and ADR-057 leaves renaming undecided. A row with a
doubled hyphen could exist: until ``489b2e8`` (2026-07-16) the API checked only
``max_length``, and this CHECK has always admitted ``--``. If one does, the upgrade
fails before changing anything and names every slug that breaks the shape, after
migration 015's precedent, and the operator decides. Postgres's own validation of the
new CHECK would fail the upgrade as well, but it names no row, which is the reason the
pre-check exists. ``tests/integration/test_clan_slug_shape.py`` pins the difference.

``downgrade`` restores 001's CHECK text exactly, under the same name.

Revision ID: 040_clan_slug_one_shape
Revises: 039_drop_clan_settings
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "040_clan_slug_one_shape"
down_revision: str | None = "039_drop_clan_settings"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_clans_clans_slug_format"
# ``_SLUG_PATTERN`` (``app/schemas/auth.py``) and ``_ClanCode``'s ``min_length``, copied
# rather than imported: a migration must keep meaning what it meant when it ran.
_ONE_SHAPE = r"char_length(slug) >= 2 AND slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'"
# ``001_initial.py:56``, verbatim.
_SHAPE_001 = r"slug ~ '^[a-z0-9][a-z0-9\-]*[a-z0-9]$'"


def upgrade() -> None:
    breaking = (
        op.get_bind()
        .execute(sa.text(f"SELECT slug FROM clans WHERE NOT ({_ONE_SHAPE}) ORDER BY slug"))
        .scalars()
        .all()
    )
    if breaking:
        raise RuntimeError(
            f"{len(breaking)} clans.slug value(s) break the clan-code shape; this migration "
            "rewrites no slug, so resolve them by hand before migrating (#190): "
            + ", ".join(repr(slug) for slug in breaking)
        )
    op.execute(f"ALTER TABLE clans DROP CONSTRAINT {_CONSTRAINT}")
    op.execute(f"ALTER TABLE clans ADD CONSTRAINT {_CONSTRAINT} CHECK ({_ONE_SHAPE})")


def downgrade() -> None:
    # Every slug the new CHECK admits, 001's admits too, so this cannot fail on data.
    op.execute(f"ALTER TABLE clans DROP CONSTRAINT {_CONSTRAINT}")
    op.execute(f"ALTER TABLE clans ADD CONSTRAINT {_CONSTRAINT} CHECK ({_SHAPE_001})")
