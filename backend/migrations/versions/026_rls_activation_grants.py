"""RLS activation Phase 1: complete the familyroots_app grants (functions/sequences).

Migration 002 created the non-bypass ``familyroots_app`` role and granted table CRUD +
default privileges on TABLES, but not EXECUTE on functions or sequence usage. Once the
request path drops to this role (SP-3 Phase 1), any query that calls a SQL function
(``find_relationship_path``, ``get_descendants_flat``, ``f_unaccent``, the lunar/tree
helpers, ``set_config`` is built-in so exempt) would fail without EXECUTE. This grants
EXECUTE on all current + future functions and USAGE/SELECT on sequences (none today —
PKs are client-side uuid4 — but future-proofed). Grants only; no table/RLS change
(``documents`` RLS is already ENABLEd from 002). Idempotent and reversible.

Revision ID: 026_rls_activation_grants
Revises: 025_audit_logs_created_at_index
"""

from __future__ import annotations

from alembic import op

revision: str = "026_rls_activation_grants"
down_revision: str | None = "025_audit_logs_created_at_index"
branch_labels = None
depends_on = None

_ROLE = "familyroots_app"


def upgrade() -> None:
    # EXECUTE on every existing function (SET LOCAL ROLE callers need these).
    op.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {_ROLE}")
    # USAGE/SELECT on sequences (none today; harmless + future-proof for serial columns).
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {_ROLE}")
    # Future objects created by the migration owner in this schema inherit the grants.
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO {_ROLE}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {_ROLE}"
    )


def downgrade() -> None:
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM {_ROLE}"
    )
    op.execute(f"REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM {_ROLE}")
    op.execute(f"REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM {_ROLE}")
