"""RLS layer-2 Phase 9 (ADR-043): audit_logs per command, notification_log by template.

Migration ``034`` covers two tables with two different policy shapes, and reading them as one
change is the mistake this file exists to prevent:

* ``notification_log_clan_isolation`` is the migration-027 template — clan-keyed on reads and
  on writes. ``clan_id`` is ``NOT NULL`` and the only accessor is the anniversary scheduler,
  which runs on a bare connection with no RLS seam. **The policy is inert today.** It guards a
  reader that does not exist yet, which ADR-043 § 2 took over a permanent exemption row in
  the coverage gate's list.
* ``audit_logs`` gets ``audit_logs_sel`` (clan-keyed SELECT), ``audit_logs_ins``
  (``WITH CHECK (true)``), and **no UPDATE or DELETE policy at all**. Reads are isolated,
  writes are not, and the two commands with no policy are denied outright for the request
  role, which is what makes the trail append-only at the database rather than by convention.

Everything below asserts at the **database layer** with naked SQL under the production seam
(``RlsSession`` + the ``app.clan_id`` ContextVar). That is not a style preference here: there
is no clan-facing API for either table, so an API-level test would prove nothing at all about
these policies. ``GET /api/v1/platform-admin/audit-log`` is the single reader of either table
and it runs privileged, so it cannot exercise a policy either.

Two vacuous-pass traps are guarded explicitly, both learned on the deny-all migration:

1. **"Zero rows" is also what an empty table returns.** Every denial assertion below is
   followed by a privileged read proving the rows were there the whole time.
2. **One direction is not isolation.** A policy that hides everything passes a one-sided test.
   Both tables are checked from clan A's side and clan B's side.

The scheduler's cross-clan run lives in ``test_scheduler_cross_clan_notification_log.py`` and
the no-clan-GUC audit write paths live in ``test_audit_write_paths_no_clan_guc.py``, because
each drives a different layer and neither belongs in a DB-layer file.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import RlsSession
from app.core.rls import set_request_clan_id
from app.domain.platform_admin.query_port import AuditLogEntryView
from app.infrastructure.persistence.platform_admin_query_port import (
    SqlAlchemyPlatformAdminQueryPort,
)

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


def _rls(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """A session with the production RLS seam attached (SET LOCAL ROLE + app.clan_id)."""
    return async_sessionmaker(
        engine, sync_session_class=RlsSession, expire_on_commit=False, class_=AsyncSession
    )


def _system(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """The privileged session class that ``get_system_db`` hands the platform-admin and
    scheduler paths (``app/core/database.py:86-93``): no seam, so no role drop and no GUC."""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# ── seeding (privileged: bypasses both policies) ──────────────────────────────


async def _clan(conn: AsyncConnection, clan_id: uuid.UUID) -> None:
    await conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:10]}"},
    )


async def _audit(
    conn: AsyncConnection,
    clan_id: uuid.UUID | None,
    *,
    action: str = "person.create",
    created_at: datetime | None = None,
) -> uuid.UUID:
    """One audit row. ``clan_id=None`` is the platform-level case the column exists for
    (``app/models/audit_log.py:18-21``)."""
    row_id = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO audit_logs (id, clan_id, actor_id, actor_role, action, "
            "resource_type, created_at) "
            "VALUES (:id, :c, :a, 'admin', :act, 'person', "
            "        coalesce(:ts, now()))"
        ),
        {"id": row_id, "c": clan_id, "a": uuid.uuid4(), "act": action, "ts": created_at},
    )
    return row_id


async def _notification(conn: AsyncConnection, clan_id: uuid.UUID) -> uuid.UUID:
    row_id = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO notification_log (id, clan_id, user_id, notification_type, "
            "title, body, status) "
            "VALUES (:id, :c, '00000000-0000-0000-0000-000000000000', "
            "        'death_anniversary', 'Giỗ', '', 'sent')"
        ),
        {"id": row_id, "c": clan_id},
    )
    return row_id


class _Seed:
    """Two clans; one audit row and one notification row each, plus one platform-level
    audit row whose ``clan_id`` is NULL and belongs to no clan by construction."""

    def __init__(
        self,
        clan_a: uuid.UUID,
        clan_b: uuid.UUID,
        audit_a: uuid.UUID,
        audit_b: uuid.UUID,
        audit_null: uuid.UUID,
        notif_a: uuid.UUID,
        notif_b: uuid.UUID,
    ) -> None:
        self.clan_a = clan_a
        self.clan_b = clan_b
        self.audit_a = audit_a
        self.audit_b = audit_b
        self.audit_null = audit_null
        self.notif_a = notif_a
        self.notif_b = notif_b

    @property
    def audit_ids(self) -> set[uuid.UUID]:
        return {self.audit_a, self.audit_b, self.audit_null}

    @property
    def notif_ids(self) -> set[uuid.UUID]:
        return {self.notif_a, self.notif_b}


async def _seed_two(engine: AsyncEngine) -> _Seed:
    clan_a, clan_b = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as conn:  # privileged connection — RLS-bypassing
        await _clan(conn, clan_a)
        await _clan(conn, clan_b)
        audit_a = await _audit(conn, clan_a)
        audit_b = await _audit(conn, clan_b)
        audit_null = await _audit(conn, None, action="platform.clan_suspend")
        notif_a = await _notification(conn, clan_a)
        notif_b = await _notification(conn, clan_b)
    return _Seed(clan_a, clan_b, audit_a, audit_b, audit_null, notif_a, notif_b)


async def _privileged_ids(engine: AsyncEngine, table: str, ids: set[uuid.UUID]) -> set[uuid.UUID]:
    """The control every denial assertion needs. ``count(*) == 0`` under the request role
    means nothing unless the table demonstrably held the rows."""
    async with engine.connect() as conn:
        return set(
            (
                await conn.execute(
                    sa.text(f"SELECT id FROM {table} WHERE id = ANY(:ids)"),
                    {"ids": list(ids)},
                )
            ).scalars()
        )


# ── audit_logs: reads are clan-keyed, in both directions ──────────────────────


async def test_audit_reads_are_scoped_to_the_active_clan_in_both_directions(
    engine: AsyncEngine,
) -> None:
    """``audit_logs_sel`` is the whole reason this table joined layer 2 (ADR-043 § 3).

    A future clan-facing audit endpoint that forgets its ``WHERE clan_id`` reads only the
    active clan anyway. Checked from both sides, because a policy that hid everything would
    satisfy one direction on its own.
    """
    seed = await _seed_two(engine)
    assert await _privileged_ids(engine, "audit_logs", seed.audit_ids) == seed.audit_ids

    rls = _rls(engine)

    set_request_clan_id(seed.clan_a)
    async with rls() as s:
        assert await s.scalar(sa.text("SELECT current_user")) == "familyroots_app"
        visible = set(
            (
                await s.execute(
                    sa.text("SELECT id FROM audit_logs WHERE id = ANY(:ids)"),
                    {"ids": list(seed.audit_ids)},
                )
            ).scalars()
        )
    assert visible == {seed.audit_a}, f"clan A saw rows it does not own: {visible}"

    set_request_clan_id(seed.clan_b)
    async with rls() as s:
        visible = set(
            (
                await s.execute(
                    sa.text("SELECT id FROM audit_logs WHERE id = ANY(:ids)"),
                    {"ids": list(seed.audit_ids)},
                )
            ).scalars()
        )
    assert visible == {seed.audit_b}, f"clan B saw rows it does not own: {visible}"

    assert await _privileged_ids(engine, "audit_logs", seed.audit_ids) == seed.audit_ids


async def test_audit_reads_fail_closed_with_no_clan_selected(engine: AsyncEngine) -> None:
    """Empty GUC → ``nullif(…)::uuid`` is NULL → the predicate is NULL → zero rows. The
    privileged read afterwards is what stops this passing on an empty table."""
    seed = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(None)
    async with rls() as s:
        assert await s.scalar(sa.text("SELECT current_setting('app.clan_id', true)")) == ""
        assert (
            await s.scalar(
                sa.text("SELECT count(*) FROM audit_logs WHERE id = ANY(:ids)"),
                {"ids": list(seed.audit_ids)},
            )
            == 0
        )
    assert await _privileged_ids(engine, "audit_logs", seed.audit_ids) == seed.audit_ids


# ── audit_logs: the NULL-clan_id pair that proves ADR-043 §§ 4 and 5 together ──


async def test_null_clan_audit_row_is_invisible_to_every_clan(engine: AsyncEngine) -> None:
    """ADR-043 § 4. ``NULL = <anything>`` is NULL in SQL, so ``audit_logs_sel`` hides a
    platform-level row from every clan with no special case, and no clan gets more access to
    it than any other.

    This is the assertion that fails if someone widens the predicate to
    ``USING (clan_id = GUC OR clan_id IS NULL)`` — the shape ADR-043 named as the one a
    reader reaches for on seeing "nullable on purpose", and which would publish every
    platform action to every clan.
    """
    seed = await _seed_two(engine)
    rls = _rls(engine)

    for clan in (seed.clan_a, seed.clan_b):
        set_request_clan_id(clan)
        async with rls() as s:
            found = await s.scalar(
                sa.text("SELECT count(*) FROM audit_logs WHERE id = :id"),
                {"id": seed.audit_null},
            )
        assert found == 0, f"clan {clan} can read a platform-level audit row"

    # The row is retained, not deleted or rewritten — nothing about the policy touches data.
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                sa.text("SELECT clan_id, action FROM audit_logs WHERE id = :id"),
                {"id": seed.audit_null},
            )
        ).one()
    assert row.clan_id is None
    assert row.action == "platform.clan_suspend"


async def test_platform_audit_surface_still_returns_null_clan_rows(engine: AsyncEngine) -> None:
    """ADR-043 § 5, through the real reader rather than through raw SQL.

    ``SqlAlchemyPlatformAdminQueryPort.get_audit_log`` is the ONLY reader of this table
    (``platform_admin_query_port.py:134-149``), reached via ``get_platform_admin_query_handler``
    which depends on ``get_system_db`` (``dependencies.py:174-177``). The system session never
    issues ``SET LOCAL ROLE``, so RLS does not apply to it and ADR-030's "across all clans,
    not only ``clan_id IS NULL``" contract is unnarrowed.

    Both halves are asserted: the platform row IS returned, and so are both clans' rows in the
    same unfiltered page. Asserting only the first would pass on a surface that had silently
    become platform-rows-only.
    """
    seed = await _seed_two(engine)
    system = _system(engine)

    async with system() as s:
        assert await s.scalar(sa.text("SELECT current_user")) != "familyroots_app"
        page = await SqlAlchemyPlatformAdminQueryPort(s).get_audit_log(
            clan_id=None, action=None, cursor=None, limit=100
        )

    returned = {e.id for e in page.data}
    assert seed.audit_null in returned, (
        "the platform audit surface lost its NULL-clan rows — migration 034 must not narrow "
        "it, and if this fails the reader has moved off get_system_db"
    )
    assert {seed.audit_a, seed.audit_b} <= returned, (
        "the platform audit surface must span clans, not only platform rows (ADR-030)"
    )

    entry: AuditLogEntryView = next(e for e in page.data if e.id == seed.audit_null)
    assert entry.clan_id is None


# ── audit_logs: writes are permitted, edits and erasures are not ──────────────


async def test_request_role_may_insert_an_audit_row_for_any_clan_or_none(
    engine: AsyncEngine,
) -> None:
    """``audit_logs_ins WITH CHECK (true)``, and each of the four cases is a real path.

    Own clan is the ordinary dispatcher write. **No GUC at all** is
    ``POST /api/v1/auth/register``, which is unauthenticated. **NULL clan_id** is a
    platform-level action. **Another clan's id** is the write-side hole ADR-043 accepts
    explicitly, because the value comes from a server-assembled ``AuditableEvent`` and never
    from client input.

    Each insert is confirmed by a **privileged** read. Confirming from the request session
    would be circular: ``audit_logs_sel`` would hide three of these four rows even though
    they landed.
    """
    seed = await _seed_two(engine)
    rls = _rls(engine)

    cases: list[tuple[str, uuid.UUID | None, uuid.UUID | None]] = [
        ("own clan", seed.clan_a, seed.clan_a),
        ("another clan", seed.clan_a, seed.clan_b),
        ("null clan", seed.clan_a, None),
        ("no clan GUC at all", None, seed.clan_a),
    ]

    written: dict[str, uuid.UUID] = {}
    for label, guc, row_clan in cases:
        set_request_clan_id(guc)
        row_id = uuid.uuid4()
        async with rls() as s:
            await s.execute(
                sa.text(
                    "INSERT INTO audit_logs (id, clan_id, actor_id, actor_role, action, "
                    "resource_type) VALUES (:id, :c, :a, 'admin', 'clan.create', 'clan')"
                ),
                {"id": row_id, "c": row_clan, "a": uuid.uuid4()},
            )
            await s.commit()
        written[label] = row_id

    landed = await _privileged_ids(engine, "audit_logs", set(written.values()))
    assert landed == set(written.values()), (
        f"an audit INSERT was rejected under the request role: "
        f"{ {k: v for k, v in written.items() if v not in landed} }"
    )


async def test_request_role_cannot_update_an_audit_row(engine: AsyncEngine) -> None:
    """No UPDATE policy → the command is denied for a non-bypass role, so it reaches no row.

    The clan GUC is set to the row's OWN clan, which is the strongest form of the claim: even
    the clan that owns the row and can read it cannot rewrite it. The check afterwards is
    privileged, because a policy that hides a row would also hide the damage.
    """
    seed = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(seed.clan_a)
    async with rls() as s:
        # Prove the row is visible first, or "0 rows updated" says nothing about UPDATE.
        assert (
            await s.scalar(
                sa.text("SELECT count(*) FROM audit_logs WHERE id = :id"), {"id": seed.audit_a}
            )
            == 1
        )
        updated = (
            (
                await s.execute(
                    sa.text(
                        "UPDATE audit_logs SET action = 'tampered' WHERE id = :id RETURNING id"
                    ),
                    {"id": seed.audit_a},
                )
            )
            .scalars()
            .all()
        )
        assert list(updated) == []
        await s.commit()

    async with engine.connect() as conn:
        action = await conn.scalar(
            sa.text("SELECT action FROM audit_logs WHERE id = :id"), {"id": seed.audit_a}
        )
    assert action == "person.create", "the audit trail is not immutable for familyroots_app"


async def test_request_role_cannot_delete_an_audit_row(engine: AsyncEngine) -> None:
    """The other half of append-only. A DELETE aimed at the clan's own audit row, from that
    clan, reaches nothing — and the row is still there when read privileged."""
    seed = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(seed.clan_a)
    async with rls() as s:
        await s.execute(
            sa.text("DELETE FROM audit_logs WHERE id = ANY(:ids)"), {"ids": list(seed.audit_ids)}
        )
        await s.commit()

    assert await _privileged_ids(engine, "audit_logs", seed.audit_ids) == seed.audit_ids


# ── notification_log: the 027 template, both directions ──────────────────────


async def test_notification_reads_are_scoped_to_the_active_clan_in_both_directions(
    engine: AsyncEngine,
) -> None:
    """The inert guard, measured anyway. Nothing reads this table on a request session today
    (``grep -rn 'notification_log' backend/app`` finds only the scheduler's two statements),
    so this is the only place the policy is exercised at all — and the only thing that would
    catch it being written as ``USING (true)``."""
    seed = await _seed_two(engine)
    assert await _privileged_ids(engine, "notification_log", seed.notif_ids) == seed.notif_ids

    rls = _rls(engine)
    for clan, own, other in (
        (seed.clan_a, seed.notif_a, seed.notif_b),
        (seed.clan_b, seed.notif_b, seed.notif_a),
    ):
        set_request_clan_id(clan)
        async with rls() as s:
            visible = set(
                (
                    await s.execute(
                        sa.text("SELECT id FROM notification_log WHERE id = ANY(:ids)"),
                        {"ids": list(seed.notif_ids)},
                    )
                ).scalars()
            )
        assert visible == {own}, f"clan {clan} saw {visible}, expected only {own} (not {other})"

    assert await _privileged_ids(engine, "notification_log", seed.notif_ids) == seed.notif_ids


async def test_notification_reads_fail_closed_with_no_clan_selected(engine: AsyncEngine) -> None:
    """No clan → NULL predicate → zero rows, with the privileged control behind it."""
    seed = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(None)
    async with rls() as s:
        assert (
            await s.scalar(
                sa.text("SELECT count(*) FROM notification_log WHERE id = ANY(:ids)"),
                {"ids": list(seed.notif_ids)},
            )
            == 0
        )
    assert await _privileged_ids(engine, "notification_log", seed.notif_ids) == seed.notif_ids


async def test_notification_write_for_another_clan_is_rejected(engine: AsyncEngine) -> None:
    """``WITH CHECK`` RAISES rather than dropping the row silently. This is where the two
    tables' shapes visibly differ: the same statement against ``audit_logs`` is ACCEPTED
    (see the insert test above), because ``audit_logs_ins`` is permissive by decision."""
    seed = await _seed_two(engine)
    rls = _rls(engine)
    set_request_clan_id(seed.clan_a)
    async with rls() as s:
        with pytest.raises(sa.exc.DBAPIError) as ei:
            await s.execute(
                sa.text(
                    "INSERT INTO notification_log (id, clan_id, user_id, notification_type, "
                    "title, body, status) VALUES (:id, :c, "
                    "'00000000-0000-0000-0000-000000000000', 'death_anniversary', 'Giỗ', "
                    "'', 'sent')"
                ),
                {"id": uuid.uuid4(), "c": seed.clan_b},
            )
            await s.flush()
        assert "row-level security" in str(ei.value).lower()


async def test_system_session_still_spans_clans_on_both_tables(engine: AsyncEngine) -> None:
    """``ENABLE``, not ``FORCE``. The privileged session is what the scheduler and the
    platform-admin surface run on, and it must see everything. If this fails, those two are
    down, not merely narrowed."""
    seed = await _seed_two(engine)
    system = _system(engine)
    async with system() as s:
        assert await s.scalar(sa.text("SELECT current_user")) != "familyroots_app"
        audit = set(
            (
                await s.execute(
                    sa.text("SELECT id FROM audit_logs WHERE id = ANY(:ids)"),
                    {"ids": list(seed.audit_ids)},
                )
            ).scalars()
        )
        notif = set(
            (
                await s.execute(
                    sa.text("SELECT id FROM notification_log WHERE id = ANY(:ids)"),
                    {"ids": list(seed.notif_ids)},
                )
            ).scalars()
        )
    assert audit == seed.audit_ids
    assert notif == seed.notif_ids


async def test_both_tables_are_rls_enabled(engine: AsyncEngine) -> None:
    """Migration 034 itself. Without this, every "privileged session still works" assertion
    above would pass for the wrong reason — an absent policy looks exactly like a working one
    from a session that bypasses."""
    async with engine.connect() as conn:
        enabled = {
            row["relname"]: row["relrowsecurity"]
            for row in (
                await conn.execute(
                    sa.text(
                        "SELECT c.relname, c.relrowsecurity FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND c.relname = ANY(:t)"
                    ),
                    {"t": ["audit_logs", "notification_log"]},
                )
            )
            .mappings()
            .all()
        }
        policies = {
            table: sorted(
                (
                    await conn.execute(
                        sa.text("SELECT policyname FROM pg_policies WHERE tablename = :t"),
                        {"t": table},
                    )
                )
                .scalars()
                .all()
            )
            for table in ("audit_logs", "notification_log")
        }

    assert enabled == {"audit_logs": True, "notification_log": True}
    assert policies["audit_logs"] == ["audit_logs_ins", "audit_logs_sel"]
    assert policies["notification_log"] == ["notification_log_clan_isolation"]
