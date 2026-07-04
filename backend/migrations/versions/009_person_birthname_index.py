"""Add a trigram index on persons.birth_name for the person search.

Person search matches ``public.f_unaccent(full_name)`` OR
``public.f_unaccent(birth_name)``. full_name already has a GIN trigram index
(idx_persons_fullname_trgm, migration 001), but birth_name had none, so the OR
branch could not be index-backed and the planner fell back to a sequential scan
for the whole query. Add the matching birth_name trigram index so both branches
use a BitmapOr of index scans.

(The full_name index itself is unchanged; the accompanying code change aligns the
query expression to `public.f_unaccent(...)` so the existing index is actually used.)

Revision ID: 009_person_birthname_index
Revises: 008_drop_change_req_trigger
"""

from __future__ import annotations

from alembic import op

revision: str = "009_person_birthname_index"
down_revision: str | None = "008_drop_change_req_trigger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX idx_persons_birthname_trgm ON persons "
        "USING gin (public.f_unaccent(birth_name) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_persons_birthname_trgm")
