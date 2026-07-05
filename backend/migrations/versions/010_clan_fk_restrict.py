"""Harden clan-owned FKs: ON DELETE CASCADE -> RESTRICT (M10).

There is no clan-delete path in the application — clans are only suspended /
reactivated. But every clan-owned foreign key was declared ON DELETE CASCADE, so a
future or manual ``DELETE FROM clans`` would silently cascade away the clan's entire
genealogy (marriages, parent-child edges, branches, memberships, invitations,
settings, change requests, notifications, documents, events). Flip those to RESTRICT
so such a delete fails loudly instead.

``persons.created_by_clan_id`` and ``audit_logs.clan_id`` deliberately stay SET NULL:
persons are de-provenanced (not destroyed) and audit rows are retained.

The FK constraint name is introspected and preserved — only the ON DELETE rule
changes — so the round trip is exact regardless of how the baseline named each FK.

Revision ID: 010_clan_fk_restrict
Revises: 009_person_birthname_index
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "010_clan_fk_restrict"
down_revision: str | None = "009_person_birthname_index"
branch_labels = None
depends_on = None

# (table, clan-referencing column) whose FK to clans.id is being hardened.
# Excludes persons + audit_logs (SET NULL, retained by design).
_CLAN_FKS: tuple[tuple[str, str], ...] = (
    ("change_requests", "clan_id"),
    ("clan_settings", "clan_id"),
    ("marriages", "created_by_clan_id"),
    ("user_clan_roles", "clan_id"),
    ("clan_invitations", "clan_id"),
    ("branches", "clan_id"),
    ("clan_memberships", "clan_id"),
    ("notification_log", "clan_id"),
    ("parent_child", "created_by_clan_id"),
    ("documents", "clan_id"),
    ("events", "clan_id"),
)


def _repoint(ondelete: str) -> None:
    """Recreate each clan FK with the given ON DELETE rule, preserving its name."""
    insp = sa.inspect(op.get_bind())
    for table, col in _CLAN_FKS:
        for fk in insp.get_foreign_keys(table):
            if fk.get("referred_table") == "clans" and col in fk.get("constrained_columns", []):
                op.drop_constraint(fk["name"], table, type_="foreignkey")
                op.create_foreign_key(fk["name"], table, "clans", [col], ["id"], ondelete=ondelete)


def upgrade() -> None:
    _repoint("RESTRICT")


def downgrade() -> None:
    _repoint("CASCADE")
