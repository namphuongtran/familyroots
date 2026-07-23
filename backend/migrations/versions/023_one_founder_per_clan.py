"""One live founder per clan — DB backstop (H3/ADR-026).

ADR-026 added ``PUT /clans/me/founder`` (Task 1) to designate/correct the
thủy tổ, but that route's "clear old founder, then set new founder" is two
statements with no DB-level backstop: a race between two admins designating
different persons concurrently, or a future non-API writer, could leave a
clan with 2+ live ``is_founder = true`` rows. ``find_clan_founder``
(``app/services/tree_builder.py``) silently picks one of them via a bare
``LIMIT 1`` with no ordering — nondeterministic which becomes "the" thủy tổ
for the graph-computed đời (generation) read model, and the second row is a
silent orphaned invariant violation, not a rejected write.

Fix: a partial unique index on ``clan_memberships (clan_id) WHERE
is_founder = true``. Partial (not a plain unique constraint on clan_id)
because the vast majority of ``clan_memberships`` rows are NOT founders —
member/blood/spouse rows for one clan are many, so the constraint must only
bind the (rare) founder-flagged rows, not every membership row for the
clan. This makes a second concurrent "set is_founder = true for this clan"
racing an existing founder row hit 23505 (unique_violation) at commit —
the race either serializes (one writer waits, then sees the other's
committed clear-then-set and its own set proceeds) or one loser's UPDATE
is rejected outright; never two live founders.

Pre-check fails the migration loudly (listing clans with >1 founder) if
legacy data already violates the invariant — no silent repair (015/021/022
precedent).

Revision ID: 023_one_founder_per_clan
Revises: 022_edge_write_serialization
"""

from __future__ import annotations

from alembic import op

revision: str = "023_one_founder_per_clan"
down_revision: str | None = "022_edge_write_serialization"
branch_labels = None
depends_on = None

_PRECHECK = """
DO $$
DECLARE bad TEXT;
BEGIN
    SELECT string_agg(v.c, '; ') INTO bad FROM (
        SELECT format('clan=%s x%s founders', clan_id, COUNT(*)) AS c
        FROM clan_memberships WHERE is_founder = true
        GROUP BY clan_id HAVING COUNT(*) > 1
    ) v;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'cannot enforce one-founder-per-clan: %', bad;
    END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(_PRECHECK)
    op.execute(
        "CREATE UNIQUE INDEX uq_clan_memberships_one_founder "
        "ON clan_memberships (clan_id) WHERE is_founder = true"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_clan_memberships_one_founder")
