"""Indexes backing live query patterns that had none.

- persons list keysets on ORDER BY (full_name, id) with a full_name cursor
  predicate; only a GIN trigram on f_unaccent(full_name) existed, which
  cannot serve ORDER BY — every page sorted the clan's whole membership join.
- documents/events cursor lists (paginate_query) order by (created_at, id)
  filtered by clan_id; only single-column clan indexes existed.
- identity_claims list_user_claims filters user_id across any status; the
  only user_id index was the partial unique WHERE status='PENDING'.
- the retention purge job scans is_deleted = true AND deleted_at < cutoff;
  idx_documents_is_deleted is partial on the OPPOSITE half (= false).
- tree recursive CTEs join parent_child on parent_id with clan + live-edge
  predicates.

Revision ID: 018_query_support_indexes
Revises: 017_notification_sent_on
"""

from __future__ import annotations

from alembic import op

revision: str = "018_query_support_indexes"
down_revision: str | None = "017_notification_sent_on"
branch_labels = None
depends_on = None

_INDEXES: tuple[tuple[str, str], ...] = (
    (
        "idx_persons_fullname_keyset",
        "CREATE INDEX idx_persons_fullname_keyset ON persons (full_name, id)",
    ),
    (
        "idx_documents_clan_created",
        "CREATE INDEX idx_documents_clan_created ON documents (clan_id, created_at, id)",
    ),
    (
        "idx_events_clan_created",
        "CREATE INDEX idx_events_clan_created ON events (clan_id, created_at, id)",
    ),
    (
        "idx_identity_claims_user_created",
        "CREATE INDEX idx_identity_claims_user_created "
        "ON identity_claims (user_id, created_at, id)",
    ),
    (
        "idx_documents_purge_due",
        "CREATE INDEX idx_documents_purge_due ON documents (deleted_at) WHERE is_deleted = true",
    ),
    (
        "idx_parent_child_parent_clan_live",
        "CREATE INDEX idx_parent_child_parent_clan_live "
        "ON parent_child (parent_id, created_by_clan_id) WHERE is_deleted = false",
    ),
)


def upgrade() -> None:
    for _, ddl in _INDEXES:
        op.execute(ddl)


def downgrade() -> None:
    for name, _ in reversed(_INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {name}")
