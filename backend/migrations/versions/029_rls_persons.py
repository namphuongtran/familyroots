"""RLS layer-2 Phase 4: clan-membership isolation on persons (ADR-008).

persons is M:N (a person belongs to clans via clan_memberships; created_by_clan_id is a
nullable ORIGIN, not membership), so it uses PER-COMMAND policies keyed on app.clan_id:

- SELECT: visible only if the person is a MEMBER of the active clan (read backstop —
  blocks cross-clan person/PII reads a missed application join would leak).
- INSERT: WITH CHECK created_by_clan_id = GUC. A membership-based WITH CHECK can't be used
  because save_with_membership inserts the person row BEFORE its clan_memberships row, so
  the check would fail; created_by_clan_id is set at insert time and equals the GUC.
- UPDATE: USING membership, WITH CHECK true (permissive) so soft-delete/restore AND
  editing a SHARED person (member here but created_by_clan_id = another clan) don't break.
- DELETE: USING membership.

Cross-clan readers (identity-claim handlers, platform-admin metrics) run on the privileged
system session and bypass this (see the composition root). Grants exist (002 + 026).
Reversible (drop policies + disable).

LOAD-BEARING INVARIANT: the tree functions (get_family_tree_flat/get_ancestors_flat/
find_relationship_path) JOIN persons, so under this policy a person is visible in the tree
only if they are a member of the clan. The tree therefore does NOT truncate ONLY BECAUSE
every edge/marriage-referenced person is a clan member — enforced by
``ensure_persons_in_clan`` on edge/marriage creation, with no membership-removal or
validator-bypassing bulk/GEDCOM-import path today. Any future path that records an edge for
a non-member person (or removes a membership while edges remain) would silently drop that
person and their subtree from the tree — it MUST preserve this invariant. Pinned by
test_rls_phase4_persons (positive: married-in spouse returns; negative:
test_non_member_edge_person_is_hidden). NOTE: this supersedes migration 005's docstring,
which pre-RLS said a non-member edge-referenced person "stays visible."

Revision ID: 029_rls_persons
Revises: 028_rls_edges
"""

from __future__ import annotations

from alembic import op

revision: str = "029_rls_persons"
down_revision: str | None = "028_rls_edges"
branch_labels = None
depends_on = None

_GUC = "nullif(current_setting('app.clan_id', true), '')::uuid"
_MEMBER = (
    f"EXISTS (SELECT 1 FROM clan_memberships m "
    f"WHERE m.person_id = persons.id AND m.clan_id = {_GUC})"
)
_POLICIES = ("persons_sel", "persons_ins", "persons_upd", "persons_del")


def upgrade() -> None:
    op.execute("ALTER TABLE persons ENABLE ROW LEVEL SECURITY")
    for name in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {name} ON persons")
    op.execute(f"CREATE POLICY persons_sel ON persons FOR SELECT USING ({_MEMBER})")
    op.execute(
        f"CREATE POLICY persons_ins ON persons FOR INSERT WITH CHECK (created_by_clan_id = {_GUC})"
    )
    op.execute(
        f"CREATE POLICY persons_upd ON persons FOR UPDATE USING ({_MEMBER}) WITH CHECK (true)"
    )
    op.execute(f"CREATE POLICY persons_del ON persons FOR DELETE USING ({_MEMBER})")


def downgrade() -> None:
    for name in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {name} ON persons")
    op.execute("ALTER TABLE persons DISABLE ROW LEVEL SECURITY")
