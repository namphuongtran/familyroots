"""RLS layer-2 Phase 8: a DENY-ALL tripwire on identity_claims (ADR-042).

**This is not clan isolation, and it must not be counted as clan isolation.** Every other
policy in this chain compares a row's clan to the ``app.clan_id`` GUC. This one compares
nothing: it is ``USING (false) WITH CHECK (false)``, so the request role sees no row and
writes no row, whatever clan is selected. ADR-042 § 2 chose that wording deliberately and
calls the result a tripwire rather than a second layer.

Why a clan predicate is not available here, in three facts ADR-042 read at source on
2026-08-22 and this migration re-read on the same day:

1. ``identity_claims`` has no ``clan_id``. ``app/models/identity_claim.py`` reaches a clan
   only through ``person_id`` at ``:32-36``, and the clan it reaches is the person's
   nullable ORIGIN (``persons.created_by_clan_id``, ``app/models/person.py:38-43``,
   ``ON DELETE SET NULL`` per ADR-009), not a membership.
2. Nothing on the request session touches this table. Both providers are privileged:
   ``get_claim_command_handler`` (``app/infrastructure/dependencies.py:144``) and
   ``get_claim_query_handler`` (``:149``) take ``Depends(get_system_db)``, whose docstring
   at ``app/core/database.py:86-93`` says it "bypasses RLS exactly like the
   scheduler/purge".
3. Two of the four claim routes have no clan context at all — ``GET /m/claims``
   (``app/api/v1/claims.py:35-43``) and ``DELETE /m/claims/{claim_id}`` (``:51-57``) depend
   only on ``require_active_user``, which resolves no clan. And
   ``POST /persons/{person_id}/claim`` (``app/api/v1/persons.py:417-424``) runs under the
   CLAIMANT's active clan, not the claimed person's, so a clan-keyed policy would reject
   the one insert the feature exists to perform.

What the tripwire buys: an engineer who wires a claims query to ``get_db`` instead of
``get_system_db`` gets zero rows and a rejected write in their own test run, instead of a
query that quietly reads every clan's claims. Today that mis-wiring leaks silently, because
``002_rls_documents_pilot.py:45`` grants ``familyroots_app`` full CRUD on every table in
``public`` and no policy stands behind the grant.

What it does not buy, in ADR-042's own words: it "catches a mis-wired SESSION. It does not
catch a missing FILTER on the correct session." The application layer stays the only clan
isolation on this table — ``list_clan_claims`` filtering the person's origin clan
(``claim_repository.py:204-205``), the ``clan_context_mismatch`` checks at
``claims.py:76-77``, ``:100-101``, ``:123-124``, and ``_verify_admin_access``
(``claim_handlers.py:117``, ``:198``). This table therefore has ONE layer where the nine
clan-isolated tables have two.

The policy is written out rather than left implicit. "RLS enabled with no policies" produces
the same deny-all in Postgres, but the coverage guard at
``tests/integration/test_rls_activation.py`` treats an enabled table with no policy as a
lockout defect and fails on it — correctly — and a named policy states intent to whoever
reads ``pg_policies`` next.

``ENABLE``, not ``FORCE``: the system path connects as a bypassing role (owner locally,
service role on Supabase), so the workflow is untouched. A deny-all table under
``FORCE ROW LEVEL SECURITY`` would lock out the system session too, which is the trap
ADR-008 lines 89-90 and ADR-042 leave for the day every table is covered.

Grants are left alone (``familyroots_app`` keeps its CRUD from ``002:45``): revoking them
would be a second mechanism for the same intent, and the policy is the one this repository
already reads.

Pinned by ``tests/integration/test_rls_phase8_identity_claims.py`` (denial both ways, the
system session still working, and the ``ON DELETE CASCADE`` from ``persons`` surviving the
policy) and by the deny-all half of the coverage guard in ``test_rls_activation.py``.
Reversible (drop policy + disable).

Revision ID: 033_rls_identity_claims
Revises: 032_rls_clan_invitations
"""

from __future__ import annotations

from alembic import op

revision: str = "033_rls_identity_claims"
down_revision: str | None = "032_rls_clan_invitations"
branch_labels = None
depends_on = None

_TABLE = "identity_claims"
_POLICY = "identity_claims_system_session_only"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
    op.execute(f"CREATE POLICY {_POLICY} ON {_TABLE} FOR ALL USING (false) WITH CHECK (false)")


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
    op.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
