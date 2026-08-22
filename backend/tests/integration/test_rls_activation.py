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
# posture (S-014, migration 034), so there are now three sets, not two.
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
    # Joined 2026-08-22 (S-010, ADR-008 Phase 10, migration 035). The migration-027
    # template, unchanged: clan_id is NOT NULL and UNIQUE, one row per clan. This one is
    # INERT for the same reason as notification_log and a stronger one — measured
    # 2026-08-22, NOTHING in `backend/app` reads or writes the table except the
    # `Clan.settings` relationship (`app/models/clan.py:35`), whose result no caller
    # consumes, and no trigger creates a row, so the table is empty in production.
    # It belongs in THIS set and not the third one: both halves of its single policy are
    # clan-keyed, unlike `audit_logs`, whose INSERT admits any clan or none.
    #
    # S-010's OTHER table, `user_clan_roles`, is deliberately absent from all three sets
    # and from the schema. Re-measured 2026-08-22: a policy on it makes `POST /auth/login`
    # answer 200 with `clan_id: null` and `GET /me/clans` return `[]` (silent), and makes
    # `POST /auth/onboard` raise `InsufficientPrivilege` on the `user_clan_roles` INSERT
    # (loud). See `migrations/versions/035_rls_clan_settings.py` and
    # `test_rls_login_two_clans.py`. Do not add it here without the ADR that decides which
    # session resolves a caller's roles.
    "clan_settings",
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

# The migration-027 predicate template, present in every clan-isolated policy's `qual`.
_GUC_MARKER = "app.clan_id"


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

    `clan_settings` joined on 2026-08-22 (S-010, migration 035), into the clan-isolated
    set, because both halves of its one policy are clan-keyed. S-010's other table,
    `user_clan_roles`, did NOT join: it is the table the authorization gate reads, and a
    policy on it downgrades the caller's permissions rather than merely hiding data. That
    half of S-010 is a decision seed, not an omission — see the comment on the set above.
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
        assert (
            rls_tables == _CLAN_ISOLATED_TABLES | _REQUEST_ROLE_DENIED_TABLES | _PER_COMMAND_TABLES
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
