"""Drop idx_persons_fullname_search, which no query can use (#395).

Migration 001 built a GIN index on ``to_tsvector('simple', public.f_unaccent(full_name))``.
An expression index serves only a query containing the same expression, and nothing in the
backend, the SQL functions or the tests calls ``to_tsvector`` or builds a tsquery. Person
search matches with ``ILIKE`` on ``public.f_unaccent(full_name)``, which
``idx_persons_fullname_trgm`` serves. So every write to ``persons`` maintained an index no
plan could choose.

Dropping it removes nothing live code reads, so it keeps the ADR-070 additive rule.
``idx_persons_fullname_trgm`` and ``idx_persons_birthname_trgm`` are untouched.

``downgrade`` recreates the index exactly as ``001_initial.py`` defines it.

Revision ID: 044_drop_unused_fullname_gin
Revises: 043_rls_off_outside_layer_2
"""

from __future__ import annotations

from alembic import op

revision: str = "044_drop_unused_fullname_gin"
down_revision: str | None = "043_rls_off_outside_layer_2"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_persons_fullname_search")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX idx_persons_fullname_search ON persons "
        "USING gin (to_tsvector('simple', public.f_unaccent(full_name)))"
    )
