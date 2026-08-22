"""RLS layer-2 activation Phase 1 (SP-3, ADR-008): the RUNTIME SEAM works.

test_rls_documents proves the DB policy under a manual ``SET LOCAL ROLE``. These prove
the app's runtime seam: the ``RlsSession`` ``after_begin`` event + the request
``ContextVar`` (``set_request_clan_id``) apply the role + ``app.clan_id`` GUC on every
transaction automatically (no manual SET), survive a commit, fail closed with no clan,
let the privileged system session bypass, and honor the ``RLS_ENABLED`` rollback switch.
Migration 026's EXECUTE grants are smoke-tested under the role.

What this file does NOT pin: these assert that the two known settings hold the right
VALUES, which stays true whether the seam writes two settings or twenty. The exact SET is
pinned by ``test_rls_seam_settings_pinned.py`` and ``tests/unit/test_rls_seam_writer_inventory.py``
(seed S-045). That gap is why ADR-008 § 2 could promise an ``app.user_id`` the seam never
wrote, for roughly two months, with every gate green — see ADR-047.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

import app.core.rls as rls_module
from app.core.database import RlsSession
from app.core.rls import set_request_clan_id

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.fixture(autouse=True)
def _reset_clan_context() -> Generator[None]:
    set_request_clan_id(None)
    yield
    set_request_clan_id(None)


async def _seed_clan_with_doc(conn: AsyncConnection, clan_id: uuid.UUID) -> uuid.UUID:
    await conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:10]}"},
    )
    doc_id = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO documents (id, clan_id, title, document_type, storage_path, created_by) "
            "VALUES (:id, :c, 't', 'photo', :sp, :cb)"
        ),
        {"id": doc_id, "c": clan_id, "sp": f"p/{doc_id.hex}", "cb": uuid.uuid4()},
    )
    return doc_id


async def _seed_two_clans(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:  # privileged (RLS-bypassing) seeding
        doc_a = await _seed_clan_with_doc(conn, clan_a)
        doc_b = await _seed_clan_with_doc(conn, clan_b)
    return clan_a, clan_b, doc_a, doc_b


async def test_seam_applies_role_and_guc_without_manual_set(engine: AsyncEngine) -> None:
    """The RlsSession event alone (driven by the ContextVar) drops to familyroots_app and
    sets app.clan_id — a naked SELECT (no app clan filter) is RLS-scoped to the clan."""
    clan_a, clan_b, doc_a, doc_b = await _seed_two_clans(engine)
    rls = async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)

    set_request_clan_id(clan_a)
    async with rls() as s:
        assert await s.scalar(sa.text("SELECT current_user")) == "familyroots_app"
        assert await s.scalar(sa.text("SELECT current_setting('app.clan_id', true)")) == str(clan_a)
        ids = set((await s.execute(sa.text("SELECT id FROM documents"))).scalars().all())
        assert ids == {doc_a}  # cross-clan doc_b invisible at the DB layer

    set_request_clan_id(clan_b)
    async with rls() as s:
        ids = set((await s.execute(sa.text("SELECT id FROM documents"))).scalars().all())
        assert ids == {doc_b}


async def test_seam_reapplies_after_commit(engine: AsyncEngine) -> None:
    """SET LOCAL / set_config are transaction-scoped, so the event must re-apply on the
    NEW transaction after a commit — otherwise post-commit queries would run privileged."""
    clan_a, _clan_b, doc_a, _doc_b = await _seed_two_clans(engine)
    rls = async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)

    set_request_clan_id(clan_a)
    async with rls() as s:
        ids1 = set((await s.execute(sa.text("SELECT id FROM documents"))).scalars().all())
        assert ids1 == {doc_a}
        await s.commit()  # ends the transaction → SET LOCAL state dropped
        # A fresh transaction begins on the next query; the event must re-apply role+GUC.
        assert await s.scalar(sa.text("SELECT current_user")) == "familyroots_app"
        ids2 = set((await s.execute(sa.text("SELECT id FROM documents"))).scalars().all())
        assert ids2 == {doc_a}  # still scoped, not privileged-all


async def test_default_deny_when_no_clan(engine: AsyncEngine) -> None:
    """No clan context → empty GUC → policy NULL → zero rows (fail closed)."""
    await _seed_two_clans(engine)
    rls = async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)
    set_request_clan_id(None)
    async with rls() as s:
        assert await s.scalar(sa.text("SELECT current_user")) == "familyroots_app"
        assert await s.scalar(sa.text("SELECT count(*) FROM documents")) == 0


async def test_system_session_bypasses_rls(engine: AsyncEngine) -> None:
    """The default (system) session class has no RLS event → privileged → sees all clans
    (required so the scheduler/purge can operate platform-wide)."""
    await _seed_two_clans(engine)
    system = async_sessionmaker(engine, expire_on_commit=False)  # default Session, no event
    set_request_clan_id(None)
    async with system() as s:
        assert await s.scalar(sa.text("SELECT current_user")) != "familyroots_app"
        assert await s.scalar(sa.text("SELECT count(*) FROM documents")) >= 2


async def test_rls_disabled_switch_is_a_privileged_noop(engine: AsyncEngine) -> None:
    """RLS_ENABLED=False (rollback switch) → the event no-ops → the request session runs
    privileged and sees all clans (the app layer still enforces isolation)."""
    # Patch the settings object the running apply_rls_context actually reads (the app is
    # imported under a duplicated module path in the test env, so app.core.config.settings
    # here can be a different instance than app.core.rls.settings).
    rls_module.settings.RLS_ENABLED = False  # type: ignore[attr-defined]
    try:
        await _seed_two_clans(engine)
        rls = async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)
        set_request_clan_id(uuid.uuid4())  # even with a clan set, the switch overrides
        async with rls() as s:
            assert await s.scalar(sa.text("SELECT current_user")) != "familyroots_app"
            assert await s.scalar(sa.text("SELECT count(*) FROM documents")) >= 2
    finally:
        rls_module.settings.RLS_ENABLED = True  # type: ignore[attr-defined]


async def test_role_grants_allow_calling_functions(engine: AsyncEngine) -> None:
    """Migration 026 EXECUTE grants: under familyroots_app a query that calls a SQL
    function (the most likely activation break) succeeds — here f_unaccent + a tree fn."""
    clan_a, _b, _da, _db = await _seed_two_clans(engine)
    rls = async_sessionmaker(engine, sync_session_class=RlsSession, expire_on_commit=False)
    set_request_clan_id(clan_a)
    async with rls() as s:
        assert await s.scalar(sa.text("SELECT public.f_unaccent('José')")) == "Jose"
        # A tree SQL function (SECURITY INVOKER) must be callable under the role.
        rid = uuid.uuid4()
        await s.execute(
            sa.text("SELECT * FROM public.find_relationship_path(:a, :b, :c)"),
            {"a": rid, "b": rid, "c": clan_a},
        )  # no rows expected; the point is it does not raise on permission


# The RLS-enabled set, split by what the policies actually DO. The split exists because
# "RLS enabled with at least one policy" is not one claim, and ADR-042 shipped the first
# table where the claims diverge (S-012, migration 033). ADR-043 then shipped a third
# posture (S-014, migration 034) and ADR-050 a fourth (S-052, migration 036), so there are
# now four sets, not two. Which tables the four are OBLIGED to cover is a separate question
# and no assertion here asked it until S-015; that gate is below the sets.
#
# CLAN-ISOLATED: every policy's USING clause compares the row's clan to the app.clan_id
# GUC, so the request role reads its own clan and nothing else, and every write it can make
# stays inside that clan — either by a clan-keyed WITH CHECK (the 027 template,
# `persons_ins`) or by a clan-keyed USING deciding which row the command may reach at all
# (`persons_upd`, `persons_del`). Note that `persons` is already split per command
# (`029_rls_persons.py:56-63`); being per-command is not what separates the third set below.
_CLAN_ISOLATED_TABLES = {
    "documents",
    "events",
    "branches",
    "parent_child",
    "marriages",
    "persons",
    "change_requests",
    "clan_memberships",
    "clan_invitations",
    # Joined 2026-08-22 (S-014, ADR-043 § 2, migration 034). The migration-027 template,
    # unchanged: clan_id is NOT NULL and the only accessor is the anniversary scheduler,
    # which runs on a bare connection with no seam and so bypasses. The policy is INERT
    # today — it guards a reader that does not exist yet. ADR-043 took that over a
    # permanent exemption row in S-015's list, on the grounds that a second place to
    # record a fact is a second place to be wrong.
    "notification_log",
    # `clan_settings` was in this set from 2026-08-22 (S-010, migration 035) until the same
    # day, when ADR-054 dropped the whole table (S-065, migration 039). It was the clearest
    # case of a policy guarding a reader that never arrived: nothing constructed a
    # `ClanSettings`, nothing created a row, and the table had no endpoint. Its name is gone
    # from here rather than moved to an exemption list, because the table is gone.
    #
    # S-010's OTHER table, `user_clan_roles`, joined the schema on 2026-08-22 (S-052,
    # ADR-050, migration 036) and it is NOT in this set. Its SELECT and INSERT policies are
    # `true` on purpose, so listing it here would pass this set's assertion (some policy's
    # USING reads the GUC — its UPDATE policy does) while telling a later reader its reads
    # are confined to one clan, which is false. It has a fourth set of its own below.
}

# REQUEST-ROLE-DENIED: the policy compares nothing. USING (false) WITH CHECK (false) locks
# the request role out of the table entirely, whatever clan is selected. It is a TRIPWIRE
# for a mis-wired session, NOT clan isolation, and ADR-042 refuses to call it a second
# layer. `identity_claims` is here because it has no clan_id to compare
# (app/models/identity_claim.py reaches a clan only through person_id at :32-36), every
# claim handler is privileged by design (dependencies.py:144, :149), and two of its four
# routes resolve no clan at all. Its clan isolation is the application layer, alone.
_REQUEST_ROLE_DENIED_TABLES = {"identity_claims"}

# APPEND-ONLY-WITH-CLAN-KEYED-READS: reads are clan-keyed, the INSERT is admitted
# unconditionally, and UPDATE and DELETE have no policy at all so they are denied.
# `audit_logs` is the only member (S-014, ADR-043 § 3, migration 034) and it fits NEITHER
# set above, which is why this third one exists rather than a name being pushed into
# whichever half it half-matches:
#
#   * it is not clan-isolated — `audit_logs_ins` is `WITH CHECK (true)`, so the request role
#     can write a row naming ANY clan, or none. That is not an oversight: two request routes
#     write an audit row with NO clan GUC at all (`POST /auth/register` is unauthenticated,
#     `POST /auth/onboard` takes `get_current_user` only, `app/api/v1/auth.py:44-49, 63-68`),
#     and a clan-keyed WITH CHECK would compare `<real clan> = NULL` and reject the whole
#     registration flow. ADR-043 accepts the write-side hole because the value comes from a
#     server-assembled `AuditableEvent` and the leak direction layer 2 exists for is READ;
#   * it is not request-role-denied either — `audit_logs_sel` is a real clan predicate, and
#     it is the guard the table was brought inside layer 2 for;
#   * and the ABSENT UPDATE/DELETE policies are load-bearing rather than missing. Under RLS
#     a command with no matching policy is denied for a non-bypass role, so the trail is
#     append-only for `familyroots_app`. Nothing else in this file would notice if someone
#     added an UPDATE policy, so the test below checks for their absence by name.
#
# Listing `audit_logs` under _CLAN_ISOLATED_TABLES would have PASSED that set's assertion
# (which only asks whether some policy's USING reads the GUC) while telling a later reader
# that its writes are confined to one clan, which is false. That is the class of silent lie
# the S-012 split exists to stop.
_PER_COMMAND_TABLES = {"audit_logs"}

# CLAN-KEYED-MUTATIONS-ONLY: SELECT and INSERT are `true`, UPDATE and DELETE are clan-keyed
# on every half they have. `user_clan_roles` is the only member (S-052, ADR-050, migration
# 036) and it fits NEITHER of the three sets above, so a fourth one exists rather than a
# name being pushed into whichever half it half-matches — the S-014 rule, applied again:
#
#   * it is not clan-isolated — two of its four policies compare nothing. The clan-less
#     readers are the authorization gate itself (`app/core/security.py:249-254`, which runs
#     BEFORE it sets the GUC at `:290`), `get_login_profile`
#     (`auth_repository.py:120-137`) and `list_clans` (`me_query_port.py:19-42`), and the
#     clan-less writer is `add_membership` (`auth_repository.py:69-88`) on both
#     `POST /auth/onboard` branches. Measured 2026-08-22: the 027 template makes login
#     answer 200 with `clan_id: null` and `/me/clans` return `[]` (silent), and makes
#     onboard raise `InsufficientPrivilege` (loud);
#   * it is not request-role-denied — the UPDATE and DELETE policies are real clan
#     predicates, and they are the guard the table was brought inside layer 2 for;
#   * and it is the MIRROR of `audit_logs`, not a copy. `audit_logs` has clan-keyed reads
#     and a permissive INSERT because a record leaks by being read. This table has
#     permissive reads and clan-keyed mutations because a capability leaks by being
#     written: `clan_repository.approve_if_pending`, `delete_role_by_id`,
#     `delete_if_pending` and `change_role_if` are all keyed on the primary key ALONE, with
#     no `clan_id` predicate, so the UPDATE/DELETE policies are the only thing at the
#     database that stops a stray `ucr_id` granting admin in another clan.
#
# Listing `user_clan_roles` under _CLAN_ISOLATED_TABLES would have PASSED that set's
# assertion, because its UPDATE policy's USING does read the GUC. That is the silent lie
# these sets exist to stop.
_CLAN_KEYED_MUTATION_TABLES = {"user_clan_roles"}

# The migration-027 predicate template, present in every clan-isolated policy's `qual`.
_GUC_MARKER = "app.clan_id"

# ---------------------------------------------------------------------------
# WHICH TABLES THE FOUR SETS ARE OBLIGED TO COVER (seed S-015)
#
# The four sets above answer "what does THIS table's policy do". None of them can answer
# "is every table that needs a policy in one of them", because each assertion iterates
# its own members: a table nobody listed is a table nobody checks. That silence is how
# all three gaps survived — S-012's deny-all, S-014's per-command reads, S-052's
# clan-keyed mutations — and it is the gap S-015 closes. Eight tables also went uncovered
# across migrations 027, 028 and 029 with every gate green, found on 2026-08-13 by
# listing `__tablename__` and grepping the migrations by hand.
#
# So the universe is read from the SCHEMA: every ordinary table in `public`. A table is
# CLAN-OWNED unless it is named in `_NOT_CLAN_OWNED_TABLES` below. The default is the
# strict one on purpose. The failure this repository has actually suffered is a table
# shipping UNCLASSIFIED, so defaulting to "global" reproduces exactly that silence, while
# defaulting to "clan-owned" turns an omission into a named failure on the day it lands.
#
# The obvious signal — "it has a clan_id column" — is NOT what decides membership, because
# it is wrong in both directions and this repository holds one instance of each:
#
#   * `identity_claims` has NO clan column at all. It reaches a clan only through
#     `person_id` (`app/models/identity_claim.py:34`) and it is in scope — ADR-042;
#   * `audit_logs.clan_id` is NULLABLE by decision, so the column's presence says nothing
#     about whether every row has an owning clan — ADR-043 § 4.
#
# The signal is used for the one job it IS sufficient for: a VETO on the list below. A
# table carrying a foreign key to `clans`, or a column whose name ends in `clan_id`, may
# never be named as not-clan-owned. That is what stops an exemption being added quietly to
# make this gate pass, and it is asserted by
# `test_the_not_clan_owned_list_names_only_tables_the_schema_agrees_are_global`.
#
# Measured 2026-08-22 at migration `036_rls_user_clan_roles`: `public` holds 18 ordinary
# tables, exactly 13 carry a clan signal, the four named below carry none, and
# `identity_claims` is the one table with no signal that is still clan-owned.
_NOT_CLAN_OWNED_TABLES: dict[str, str] = {
    "alembic_version": (
        "Alembic's own migration bookkeeping, created by the tool and not by this "
        "repository's schema (`backend/migrations/env.py`). One column, one row, no "
        "application data. No ADR, because there is no decision here to record."
    ),
    "clans": (
        "The tenant registry itself. A `clans` row IS a tenant rather than a row "
        "belonging to one, so there is no owning clan for a policy to key on. ADR-008 "
        "keeps it outside layer 2: its `Not yet` paragraph excludes the auth-flow tables "
        "because `get_current_clan_id` reads them before it sets the GUC, and its "
        "Phase-11 amendment restates `clans remains outside layer 2` after ADR-050 "
        "brought `user_clan_roles` in "
        "(`docs/decisions/008-rls-defense-in-depth.md:227`, `:239-242`). ADR-002 is the "
        "tenancy model the table comes from."
    ),
    "user_profiles": (
        "The per-user identity record, keyed to a Supabase auth user. A profile exists "
        "before any clan and may belong to several, so no single clan owns the row. Its "
        "only path to `clans` is the nullable `person_id` link "
        "(`app/models/user_profile.py:38`, ON DELETE SET NULL), which is an optional "
        "self-link and not provenance. NO ADR DECIDES THIS. ADR-048 and ADR-050 each "
        "state as a fact that the table carries no policy "
        "(`048-invitation-accept-runs-on-the-system-session.md:144`, "
        "`050-user-clan-roles-clan-keyed-mutations.md:224`); neither decides that it "
        "should not. S-015 recorded the decision as owed rather than citing an ADR that "
        "does not say it."
    ),
    "user_fcm_tokens": (
        "One row per device push token, owned by a user and not by a clan. `user_id` is "
        "its only foreign key (`app/models/user_fcm_token.py:24`) and every statement "
        "against it keys on the token or the user "
        "(`app/infrastructure/persistence/auth_repository.py:165`, `:175`, "
        "`app/services/notification.py:43`). `docs/architecture/data-model.md:701-712` "
        "is the table's own description. NO ADR DECIDES THIS either — the same owed row "
        "as `user_profiles`."
    ),
}


async def _public_base_tables(conn: AsyncConnection) -> set[str]:
    """Every ordinary table in `public`, read from the catalog rather than from a list.

    This is the half of the gate that cannot go stale: a table added by a migration is in
    here the moment the migration runs, whether or not anybody remembered to classify it.
    """
    rows = (
        await conn.execute(
            sa.text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n "
                "ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r'"
            )
        )
    ).scalars()
    return {str(name) for name in rows.all()}


async def _tables_carrying_a_clan_signal(conn: AsyncConnection) -> set[str]:
    """Tables with a foreign key to `clans`, or a column whose name ends in ``clan_id``.

    Both signals are read, not one. The foreign key is the load-bearing one; the column
    name catches a `clan_id` that ships without a constraint, which is a shape no
    migration here has used yet and which the foreign-key query alone would miss.

    This set is never used to decide that a table IS clan-owned — see the comment above
    for the two tables that prove it cannot be. It is used only to refuse an entry in
    ``_NOT_CLAN_OWNED_TABLES``.
    """
    by_fk = (
        await conn.execute(
            sa.text(
                "SELECT DISTINCT child.relname FROM pg_constraint k "
                "JOIN pg_class child ON child.oid = k.conrelid "
                "JOIN pg_class parent ON parent.oid = k.confrelid "
                "JOIN pg_namespace n ON n.oid = child.relnamespace "
                "WHERE k.contype = 'f' AND n.nspname = 'public' AND parent.relname = 'clans'"
            )
        )
    ).scalars()
    columns = (
        (
            await conn.execute(
                sa.text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public'"
                )
            )
        )
        .mappings()
        .all()
    )
    by_column = {
        str(row["table_name"]) for row in columns if str(row["column_name"]).endswith("clan_id")
    }
    return {str(name) for name in by_fk.all()} | by_column


async def test_rls_coverage_enabled_tables_have_policy_and_grants(engine: AsyncEngine) -> None:
    """CI guard (ADR-008): every table with RLS ENABLEd must have at least one policy
    (else it is a silent lockout) AND familyroots_app must hold table privileges. Also
    pins the CURRENT scope, table by table — a later phase updates this set deliberately
    when it adds one.

    `clan_invitations` joined on 2026-08-22 (S-043, ADR-048, migration 032). It could not
    before, because accept-by-token ran on the request session with no clan selected;
    ADR-048 moved accept to its own privileged provider, which is what made the policy
    safe. See test_rls_phase7_clan_invitations and test_invitation_accept_no_clan_context.

    `identity_claims` joined on 2026-08-22 too (S-012, ADR-042, migration 033) and is
    **enumerated separately on purpose**. Its policy is deny-all. A guard that only asked
    "is RLS on, and is there a policy" would answer yes for it and mean nothing by it —
    the table has ONE layer of clan isolation, in the application layer, where the nine
    above have two. Adding its name to the clan-isolated set would be a lie a later reader
    could not detect, so the two sets are asserted with different questions below.

    `notification_log` and `audit_logs` joined on 2026-08-22 (S-014, ADR-043, migration
    034), and they went into DIFFERENT sets: `notification_log` takes the 027 template
    unchanged, while `audit_logs` gets clan-keyed reads, permissive inserts, and no
    UPDATE/DELETE policy at all. That third shape is `_PER_COMMAND_TABLES`.

    `clan_settings` joined the clan-isolated set on 2026-08-22 (S-010, migration 035) and
    LEFT it the same day, when ADR-054 dropped the table (S-065, migration 039). A name
    leaves this file when its table leaves the schema; it is not moved to an exemption list.

    `user_clan_roles` joined on 2026-08-22 too (S-052, ADR-050, migration 036), into a
    FOURTH set. It is the table the authorization gate reads, so a policy on it decides
    what a caller may DO rather than merely what it may see: its SELECT and INSERT are
    permissive by decision and only its UPDATE and DELETE are clan-keyed. Four postures now
    exist and each is asserted with its own question below.
    """
    async with engine.connect() as conn:
        rls_tables = set(
            (
                await conn.execute(
                    sa.text(
                        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = "
                        "c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r' "
                        "AND c.relrowsecurity"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert rls_tables == (
            _CLAN_ISOLATED_TABLES
            | _REQUEST_ROLE_DENIED_TABLES
            | _PER_COMMAND_TABLES
            | _CLAN_KEYED_MUTATION_TABLES
        ), f"RLS scope drifted: {rls_tables}"

        for table in rls_tables:
            n_policies = await conn.scalar(
                sa.text("SELECT count(*) FROM pg_policies WHERE tablename = :t"), {"t": table}
            )
            assert n_policies and n_policies >= 1, f"{table} has RLS but no policy (lockout)"
            has_select = await conn.scalar(
                sa.text("SELECT has_table_privilege('familyroots_app', :t, 'SELECT')"),
                {"t": table},
            )
            assert has_select is True, f"familyroots_app lacks SELECT on {table}"


async def test_the_not_clan_owned_list_names_only_tables_the_schema_agrees_are_global(
    engine: AsyncEngine,
) -> None:
    """``_NOT_CLAN_OWNED_TABLES`` is the one hand-written half of the gate below, so it is
    the half somebody under time pressure can edit to make a red gate go green. Three
    readings stop that, and every one of them comes from the catalog rather than from the
    list itself:

    * a name that is not a real table is a stale entry. It would silently shrink the
      universe if the table were ever re-added under the same name;
    * a name carrying a **clan signal** — a foreign key to ``clans``, or a column ending
      in ``clan_id`` — may not be there at all. This is the assertion that makes an
      exemption cost something: the two shapes the signal misses (``identity_claims``
      with no clan column, ``audit_logs`` with a nullable one) both argue that the signal
      is too weak to INCLUDE a table, and neither weakens it as a refusal to EXCLUDE one;
    * a name that already has RLS enabled or a policy is a contradiction. Somebody
      covered the table and left it classified as global, and the four posture sets below
      would go on ignoring it.
    """
    async with engine.connect() as conn:
        tables = await _public_base_tables(conn)
        signalled = await _tables_carrying_a_clan_signal(conn)
        covered = {
            str(name)
            for name in (
                await conn.execute(
                    sa.text(
                        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON "
                        "n.oid = c.relnamespace WHERE n.nspname = 'public' AND "
                        "c.relkind = 'r' AND c.relrowsecurity"
                    )
                )
            )
            .scalars()
            .all()
        }
        policied = {
            str(name)
            for name in (
                await conn.execute(
                    sa.text(
                        "SELECT DISTINCT tablename FROM pg_policies WHERE schemaname = 'public'"
                    )
                )
            )
            .scalars()
            .all()
        }

    exempt = set(_NOT_CLAN_OWNED_TABLES)

    assert not exempt - tables, (
        f"_NOT_CLAN_OWNED_TABLES names {sorted(exempt - tables)}, which is not a table in "
        f"`public`. Delete the entry — a stale name silently shrinks the universe the "
        f"coverage gate reads"
    )

    assert not exempt & signalled, (
        f"{sorted(exempt & signalled)} is listed as NOT clan-owned, but the schema says "
        f"otherwise: the table has a foreign key to `clans` or a column ending in "
        f"`clan_id`. A table with an owning clan is clan-owned. Give it a policy and put "
        f"it in one of the four posture sets — do not exempt it, and do not widen this "
        f"assertion"
    )

    assert not exempt & (covered | policied), (
        f"{sorted(exempt & (covered | policied))} is listed as NOT clan-owned, yet it has "
        f"row-level security enabled or carries a policy. One of the two is wrong. If the "
        f"table was brought inside layer 2, remove its entry here and add it to the "
        f"posture set that matches what its policy DOES"
    )


async def test_every_clan_owned_table_is_covered_by_exactly_one_of_the_four_postures(
    engine: AsyncEngine,
) -> None:
    """The gate seed S-015 exists for: a clan-owned table in NONE of the four sets fails.

    Every other assertion in this file iterates a set and asks what its members' policies
    do. That leaves the complement silent, and the complement is where every gap this file
    has ever had was found — a name in no set is a name no question is asked about. Here
    the direction is reversed: the schema names the tables, and each one has to appear.

    Four failures, and the first is the one a drop-a-policy control does not reach:

    * a clan-owned table in none of the four sets. That is a NEW table shipping with no
      policy, or with a policy in a shape nobody anticipated. It is silent today;
    * a set naming a table that is not clan-owned — a typo, or a global table pushed into
      a set to quiet the assertion above;
    * a table in two sets at once, which makes "the posture" ambiguous and lets one set's
      weaker question stand in for another's;
    * a clan-owned table with row-level security disabled, or enabled with no policy at
      all. RLS off is the silent one: the older guard enumerated `relrowsecurity` tables
      and so could not see a table that never had it switched on.
    """
    all_sets = {
        "_CLAN_ISOLATED_TABLES": _CLAN_ISOLATED_TABLES,
        "_REQUEST_ROLE_DENIED_TABLES": _REQUEST_ROLE_DENIED_TABLES,
        "_PER_COMMAND_TABLES": _PER_COMMAND_TABLES,
        "_CLAN_KEYED_MUTATION_TABLES": _CLAN_KEYED_MUTATION_TABLES,
    }
    classified: set[str] = set()
    for name, members in all_sets.items():
        overlap = classified & members
        assert not overlap, (
            f"{sorted(overlap)} is in {name} and in another posture set as well. Each set "
            f"asks a different question, so a table in two of them has whichever posture "
            f"the reader happens to look at first"
        )
        classified |= members

    async with engine.connect() as conn:
        tables = await _public_base_tables(conn)
        rls_on = {
            str(name)
            for name in (
                await conn.execute(
                    sa.text(
                        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON "
                        "n.oid = c.relnamespace WHERE n.nspname = 'public' AND "
                        "c.relkind = 'r' AND c.relrowsecurity"
                    )
                )
            )
            .scalars()
            .all()
        }
        policy_counts = {
            str(row["tablename"]): int(row["n"])
            for row in (
                (
                    await conn.execute(
                        sa.text(
                            "SELECT tablename, count(*) AS n FROM pg_policies "
                            "WHERE schemaname = 'public' GROUP BY tablename"
                        )
                    )
                )
                .mappings()
                .all()
            )
        }

        clan_owned = tables - set(_NOT_CLAN_OWNED_TABLES)

        assert not clan_owned - classified, (
            f"{sorted(clan_owned - classified)} is a clan-owned table in NONE of the four "
            f"posture sets, so nothing in this repository checks what its policies do. "
            f"Decide its posture and add it to the set that matches — or, if it is not "
            f"clan-owned, add it to _NOT_CLAN_OWNED_TABLES with the reason and the ADR "
            f"that decided it. Do not pick whichever set makes this pass: the last three "
            f"tables that fitted no set (identity_claims, audit_logs, user_clan_roles) "
            f"each PASSED an existing set's assertion while lying to the next reader"
        )

        assert not classified - clan_owned, (
            f"{sorted(classified - clan_owned)} is named in a posture set but is not a "
            f"clan-owned table in this schema — it does not exist, or it is in "
            f"_NOT_CLAN_OWNED_TABLES. A set member nobody can look up pins nothing"
        )

        for table in sorted(clan_owned):
            assert table in rls_on, (
                f"{table} is clan-owned but row-level security is DISABLED on it, so its "
                f"policies (if any) do nothing and layer 2 is absent for the table. This "
                f"is the shape a drop-the-policy control never reaches: the older coverage "
                f"guard enumerated only tables that already had RLS switched on"
            )
            assert policy_counts.get(table, 0) >= 1, (
                f"{table} is clan-owned with RLS enabled and NO policy, which is a silent "
                f"lockout: familyroots_app reads zero rows and nothing raises"
            )
            has_select = await conn.scalar(
                sa.text("SELECT has_table_privilege('familyroots_app', :t, 'SELECT')"),
                {"t": table},
            )
            assert has_select is True, (
                f"familyroots_app lacks SELECT on the clan-owned table {table}; migration "
                f"026's grants did not reach it"
            )


async def test_each_half_of_the_rls_set_matches_what_its_policies_do(engine: AsyncEngine) -> None:
    """The split above is only worth having if it is CHECKED, not merely written down.

    A comment saying "these nine isolate by clan and this one denies everything" goes stale
    the first time a migration moves a table between the halves, and nothing would notice.
    So each half is asserted with the question that belongs to it:

    * a clan-isolated table must have at least one policy whose USING clause reads the
      ``app.clan_id`` GUC — a table listed here whose policy turned into ``USING (false)``
      is locked out, not isolated, and its routes would be quietly returning nothing;
    * a request-role-denied table must have every policy reading ``USING (false)`` and
      ``WITH CHECK (false)`` — a table listed here whose policy started permitting rows
      would be handing the request role a table that ADR-042 promises it cannot reach.

    Note the second half also fails if someone "fixes" the deny-all by giving
    ``identity_claims`` a clan predicate. That is a real decision (it would reopen ADR-042
    and break ``GET /m/claims``), and it should have to be made deliberately here rather
    than arriving as a passing migration.
    """
    async with engine.connect() as conn:
        rows = (
            (
                await conn.execute(
                    sa.text(
                        "SELECT tablename, policyname, qual, with_check FROM pg_policies "
                        "WHERE schemaname = 'public'"
                    )
                )
            )
            .mappings()
            .all()
        )

    by_table: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_table.setdefault(row["tablename"], []).append(dict(row))

    for table in _CLAN_ISOLATED_TABLES:
        policies = by_table.get(table, [])
        assert policies, f"{table} is listed as clan-isolated but has no policy at all"
        assert any(_GUC_MARKER in (p["qual"] or "") for p in policies), (
            f"{table} is listed as clan-isolated but no policy's USING clause reads "
            f"{_GUC_MARKER!r}: {policies}"
        )

    for table in _REQUEST_ROLE_DENIED_TABLES:
        policies = by_table.get(table, [])
        assert policies, f"{table} is listed as request-role-denied but has no policy at all"
        for p in policies:
            assert (p["qual"] or "").strip().lower() == "false", (
                f"{table}.{p['policyname']} is enumerated as deny-all but its USING clause "
                f"is {p['qual']!r}. If this table now carries real clan isolation, move it "
                f"to _CLAN_ISOLATED_TABLES and reopen ADR-042 — do not widen this assertion"
            )
            assert (p["with_check"] or "").strip().lower() == "false", (
                f"{table}.{p['policyname']} is enumerated as deny-all but its WITH CHECK "
                f"clause is {p['with_check']!r}"
            )


async def test_audit_logs_reads_are_clan_keyed_and_it_cannot_be_edited_or_erased(
    engine: AsyncEngine,
) -> None:
    """The third set's own question, and none of the assertions above ask it.

    ADR-043 § 3 gives ``audit_logs`` three separate promises, and each one fails silently in
    a different way if it drifts:

    * ``audit_logs_sel`` is a real clan predicate. If it were widened to
      ``USING (clan_id = GUC OR clan_id IS NULL)`` — the shape ADR-043 named as the one a
      reader reaches for on seeing "nullable on purpose" — every platform-level action would
      become readable by every clan, and every other test in this repository would still
      pass.
    * ``audit_logs_ins`` is ``WITH CHECK (true)`` **on purpose**. Someone "tightening" it to
      the 027 template would break ``POST /auth/register``, which is unauthenticated and has
      no clan GUC to compare against. The HTTP tests in
      ``test_rls_phase9_audit_notification.py`` catch that; this line names the reason.
    * there is **no** UPDATE and **no** DELETE policy, which is what makes the trail
      append-only for the request role. An added policy here would hand ``familyroots_app``
      the ability to edit or erase its own audit rows, and nothing else would notice.

    ``cmd`` is read from ``pg_policies`` rather than inferred from the policy name, because a
    name is a comment and ``cmd`` is the thing Postgres enforces.
    """
    async with engine.connect() as conn:
        rows = (
            (
                await conn.execute(
                    sa.text(
                        "SELECT policyname, cmd, qual, with_check FROM pg_policies "
                        "WHERE schemaname = 'public' AND tablename = 'audit_logs'"
                    )
                )
            )
            .mappings()
            .all()
        )

    by_cmd = {r["cmd"]: dict(r) for r in rows}
    assert len(by_cmd) == len(rows), f"two policies share a command on audit_logs: {rows}"
    assert set(by_cmd) == {"SELECT", "INSERT"}, (
        f"audit_logs must carry exactly a SELECT and an INSERT policy and nothing else — "
        f"an UPDATE or DELETE policy would make the trail mutable for familyroots_app, and "
        f"a missing SELECT policy would take away the clan guard. Found: {rows}"
    )

    select_policy = by_cmd["SELECT"]
    assert _GUC_MARKER in (select_policy["qual"] or ""), (
        f"audit_logs_sel must key reads on the {_GUC_MARKER!r} GUC; found "
        f"{select_policy['qual']!r}. Note that widening this to `OR clan_id IS NULL` is the "
        f"exact predicate ADR-043 rejected: it publishes every platform-level action to "
        f"every clan"
    )
    assert "is null" not in (select_policy["qual"] or "").lower(), (
        f"audit_logs_sel has grown a NULL branch: {select_policy['qual']!r}. NULL-clan rows "
        f"are meant to be invisible to every clan (ADR-043 § 4) and visible only to the "
        f"platform-admin surface, which bypasses RLS entirely"
    )

    insert_policy = by_cmd["INSERT"]
    assert (insert_policy["with_check"] or "").strip().lower() == "true", (
        f"audit_logs_ins must stay permissive; found {insert_policy['with_check']!r}. "
        f"POST /auth/register is unauthenticated and writes an audit row with no clan GUC, "
        f"so a clan-keyed WITH CHECK here compares <real clan> = NULL and rejects it"
    )


async def test_user_clan_roles_mutations_are_clan_keyed_and_its_reads_are_not(
    engine: AsyncEngine,
) -> None:
    """The fourth set's own question, and none of the assertions above ask it.

    ADR-050 gives ``user_clan_roles`` four promises, and each one fails differently:

    * ``user_clan_roles_upd`` and ``user_clan_roles_del`` are real clan predicates. They
      are the ONLY thing at the database standing between a stray ``ucr_id`` and an admin
      grant in another clan, because all four statements that reach them
      (``clan_repository.approve_if_pending``, ``delete_role_by_id``, ``delete_if_pending``,
      ``change_role_if``) are keyed on the primary key alone. Widen either to ``USING
      (true)`` and every other test in this file still passes.
    * ``user_clan_roles_upd`` must keep its ``WITH CHECK`` too, or an UPDATE could rewrite a
      row's ``clan_id`` and hand another clan a member it never approved.
    * ``user_clan_roles_sel`` is ``USING (true)`` **on purpose**. Someone "tightening" it to
      the 027 template makes ``POST /auth/login`` answer 200 with ``clan_id: null`` and
      ``GET /me/clans`` return ``[]``, with nothing raised and nothing logged. The end-to-end
      proof is ``test_rls_login_two_clans.py``; this line names the reason.
    * ``user_clan_roles_ins`` is ``WITH CHECK (true)`` on purpose for the same shape of
      reason on the write side: both ``POST /auth/onboard`` branches insert the caller's own
      membership with no clan selected, and a clan-keyed check answers 500.

    ``cmd`` is read from ``pg_policies`` rather than inferred from the policy name, because a
    name is a comment and ``cmd`` is the thing Postgres enforces.
    """
    for table in _CLAN_KEYED_MUTATION_TABLES:
        async with engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        sa.text(
                            "SELECT policyname, cmd, qual, with_check FROM pg_policies "
                            "WHERE schemaname = 'public' AND tablename = :t"
                        ),
                        {"t": table},
                    )
                )
                .mappings()
                .all()
            )

        by_cmd = {r["cmd"]: dict(r) for r in rows}
        assert len(by_cmd) == len(rows), f"two policies share a command on {table}: {rows}"
        assert set(by_cmd) == {"SELECT", "INSERT", "UPDATE", "DELETE"}, (
            f"{table} must carry exactly one policy per command. A missing UPDATE or DELETE "
            f"policy DENIES that command to familyroots_app, which would break clan member "
            f"management outright; a missing SELECT or INSERT policy denies login and "
            f"onboarding. Found: {rows}"
        )

        for cmd in ("UPDATE", "DELETE"):
            policy = by_cmd[cmd]
            assert _GUC_MARKER in (policy["qual"] or ""), (
                f"{table} {cmd} must key on the {_GUC_MARKER!r} GUC; found {policy['qual']!r}. "
                f"This is the guard ADR-050 exists for: every statement that reaches it is "
                f"keyed on the primary key alone, with no clan_id predicate of its own"
            )
        assert _GUC_MARKER in (by_cmd["UPDATE"]["with_check"] or ""), (
            f"{table} UPDATE lost its WITH CHECK ({by_cmd['UPDATE']['with_check']!r}). Without "
            f"it an UPDATE can rewrite a row's clan_id and move a membership into a clan that "
            f"never approved it"
        )

        assert (by_cmd["SELECT"]["qual"] or "").strip().lower() == "true", (
            f"{table} SELECT is enumerated as permissive-by-decision but its USING clause is "
            f"{by_cmd['SELECT']['qual']!r}. If the clan-less readers named in ADR-050 § 1 have "
            f"moved off the request session, move this table to _CLAN_ISOLATED_TABLES and "
            f"amend ADR-050 — do not widen this assertion"
        )
        assert (by_cmd["INSERT"]["with_check"] or "").strip().lower() == "true", (
            f"{table} INSERT is enumerated as permissive-by-decision but its WITH CHECK is "
            f"{by_cmd['INSERT']['with_check']!r}. POST /auth/onboard writes the caller's own "
            f"membership with no clan GUC, so a clan-keyed check compares <real clan> = NULL"
        )
