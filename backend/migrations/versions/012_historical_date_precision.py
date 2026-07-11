"""HistoricalDate foundation: precision/display columns + backfill from `approx`.

Adds storage for date precision (`exact` | `circa` | `unknown`) and a free-text
display string alongside every date-bearing column, so a later task (Task 5) can
introduce the richer HistoricalDate value object and retire the old boolean
`*_approx` flags without a lossy migration in between. `birth_date_approx` /
`death_date_approx` are intentionally KEPT here — they still drive the backfill
below and are dropped in Task 5.

Precision columns are `NOT NULL DEFAULT 'exact'` (server_default), matching how
other enum-ish string columns in this schema (e.g. marriages.status,
persons.nationality) are modeled: the server_default guarantees existing rows get
a value the instant the column is added, and new rows get it even if the ORM
insert omits the field. The subsequent UPDATE overwrites that default with the
real per-row precision derived from the legacy `approx` flag / date presence.
Display columns are nullable free text with no default.

Backfill rules (see task brief):
  - persons: `approx` true -> 'circa'; date present (not approx) -> 'exact';
    date NULL -> 'unknown'. Applied to both birth and death independently.
  - events: `event_date` is NOT NULL in the schema, so precision is always
    'exact' after backfill (the CASE is written generally regardless).
  - marriages: `marriage_date` / `divorce_date` are nullable with no `approx`
    flag -> 'exact' when the date is present, else 'unknown'.

Revision ID: 012_historical_date_precision
Revises: 011_path_tiebreak
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "012_historical_date_precision"
down_revision: str | None = "011_path_tiebreak"
branch_labels = None
depends_on = None

# (table, precision_column, display_column) added by this migration.
_PRECISION_DISPLAY_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("persons", "birth_date_precision", "birth_date_display"),
    ("persons", "death_date_precision", "death_date_display"),
    ("events", "event_date_precision", "event_date_display"),
    ("marriages", "marriage_date_precision", "marriage_date_display"),
    ("marriages", "divorce_date_precision", "divorce_date_display"),
)


def upgrade() -> None:
    for table, precision_col, display_col in _PRECISION_DISPLAY_COLUMNS:
        op.add_column(
            table,
            sa.Column(
                precision_col,
                sa.String(10),
                nullable=False,
                server_default=sa.text("'exact'"),
            ),
        )
        op.add_column(table, sa.Column(display_col, sa.String(100), nullable=True))

    op.execute(
        "UPDATE persons SET "
        "birth_date_precision = CASE "
        "  WHEN birth_date_approx THEN 'circa' "
        "  WHEN birth_date IS NOT NULL THEN 'exact' "
        "  ELSE 'unknown' END, "
        "death_date_precision = CASE "
        "  WHEN death_date_approx THEN 'circa' "
        "  WHEN death_date IS NOT NULL THEN 'exact' "
        "  ELSE 'unknown' END"
    )
    op.execute(
        "UPDATE events SET "
        "event_date_precision = CASE "
        "  WHEN event_date IS NOT NULL THEN 'exact' "
        "  ELSE 'unknown' END"
    )
    op.execute(
        "UPDATE marriages SET "
        "marriage_date_precision = CASE "
        "  WHEN marriage_date IS NOT NULL THEN 'exact' "
        "  ELSE 'unknown' END, "
        "divorce_date_precision = CASE "
        "  WHEN divorce_date IS NOT NULL THEN 'exact' "
        "  ELSE 'unknown' END"
    )


def downgrade() -> None:
    for table, precision_col, display_col in reversed(_PRECISION_DISPLAY_COLUMNS):
        op.drop_column(table, display_col)
        op.drop_column(table, precision_col)
