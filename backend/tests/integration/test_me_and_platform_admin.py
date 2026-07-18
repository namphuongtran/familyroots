"""Coverage for the previously-untested me + platform_admin contexts (2026-06-28 review).

- me.list_clans returns only APPROVED memberships; select_clan 403s a non-member.
- platform_admin suspend/reactivate flips clan.is_active and writes an audit row.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.application.clan.commands import UpdateClan
from app.application.clan.handlers import ClanCommandHandler
from app.application.me.handlers import MeQueryHandler
from app.application.platform_admin.handlers import (
    PlatformAdminCommandHandler,
    PlatformAdminQueryHandler,
)
from app.domain.platform_admin.query_port import (
    AuditLogEntryView,
    ClanDetailView,
    ClanStatsView,
    ClanSummaryView,
    Page,
    PlatformMetricsView,
)
from app.domain.shared.exceptions import BusinessRuleViolation, ForbiddenError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.clan_repository import SqlAlchemyClanRepository
from app.infrastructure.persistence.me_query_port import SqlAlchemyMeQueryPort
from app.infrastructure.persistence.platform_admin_query_port import (
    SqlAlchemyPlatformAdminQueryPort,
)
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


async def _clan(s: AsyncSession, cid: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sl)"),
        {"id": cid, "sl": f"c-{cid.hex[:8]}"},
    )


async def _profile(s: AsyncSession, uid: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :e, 'U')"),
        {"id": uid, "e": f"u-{uid.hex[:8]}@ex.com"},
    )


async def _role(s: AsyncSession, uid: uuid.UUID, cid: uuid.UUID, *, approved: bool) -> None:
    now = datetime.now(UTC)
    await s.execute(
        sa.text(
            "INSERT INTO user_clan_roles "
            "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
            "VALUES (:u, :c, 'admin', :ap, :ab, :at)"
        ),
        {
            "u": uid,
            "c": cid,
            "ap": approved,
            "ab": uid if approved else None,
            "at": now if approved else None,
        },
    )


async def test_me_lists_only_approved_and_blocks_non_member(async_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    user_id = uuid.uuid4()
    approved_clan, pending_clan, other_clan = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        for cid in (approved_clan, pending_clan, other_clan):
            await _clan(s, cid)
        await _profile(s, user_id)
        await _role(s, user_id, approved_clan, approved=True)
        await _role(s, user_id, pending_clan, approved=False)  # pending → excluded
        await s.commit()

        handler = MeQueryHandler(SqlAlchemyMeQueryPort(s))

        clans = await handler.list_clans(user_id=str(user_id))
        ids = {c["clan_id"] for c in clans["clans"]}
        assert ids == {str(approved_clan)}  # only the approved membership
        assert clans["count"] == 1

        # select an approved clan → ok
        selected = await handler.select_clan(user_id=str(user_id), clan_id=approved_clan)
        assert selected["clan_id"] == str(approved_clan)

        # select a clan the user is not an approved member of → 403
        with pytest.raises(ForbiddenError):
            await handler.select_clan(user_id=str(user_id), clan_id=other_clan)
        with pytest.raises(ForbiddenError):
            await handler.select_clan(user_id=str(user_id), clan_id=pending_clan)


async def _audit(
    s: AsyncSession, clan_id: uuid.UUID | None, actor_id: uuid.UUID, action: str
) -> None:
    await s.execute(
        sa.text(
            "INSERT INTO audit_logs (id, clan_id, actor_id, actor_role, action, resource_type) "
            "VALUES (:id, :c, :a, 'admin', :act, 'clan')"
        ),
        {"id": uuid.uuid4(), "c": clan_id, "a": actor_id, "act": action},
    )


async def test_platform_admin_query_port_returns_typed_read_models(
    async_engine: AsyncEngine,
) -> None:
    """L4: the read-side port returns typed frozen-dataclass views with REAL field
    types (uuid.UUID/datetime), not str-ified dicts. Reverting the infra to the old
    hand-built ``str(id)`` dicts fails every ``isinstance`` assertion below."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, actor_id = uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        await _clan(s, clan_id)
        await _profile(s, actor_id)
        await _audit(s, clan_id, actor_id, "clan.suspend")
        await s.commit()

        port = SqlAlchemyPlatformAdminQueryPort(s)

        detail = await port.get_clan_detail(clan_id)
        assert isinstance(detail, ClanDetailView)
        assert isinstance(detail.id, uuid.UUID)  # a real UUID, NOT str(clan.id)
        assert detail.name == "C"
        assert isinstance(detail.stats, ClanStatsView)
        assert detail.stats.total_members >= 0

        metrics = await port.get_metrics()
        assert isinstance(metrics, PlatformMetricsView)
        assert isinstance(metrics.total_clans, int)
        assert metrics.total_clans >= 1
        assert metrics.suspended_clans == metrics.total_clans - metrics.active_clans

        clan_page = await port.list_clans(None, 20)
        assert isinstance(clan_page, Page)
        assert clan_page.meta.limit == 20
        assert all(isinstance(c, ClanSummaryView) for c in clan_page.data)
        assert all(isinstance(c.id, uuid.UUID) for c in clan_page.data)

        # Scoped to this test's own clan_id so it is deterministic despite the
        # session-scoped DB accumulating audit_log rows across the whole suite.
        audit_page = await port.get_audit_log(clan_id, None, None, 20)
        assert isinstance(audit_page, Page)
        entries = [e for e in audit_page.data if e.actor_id == actor_id]
        assert entries and isinstance(entries[0], AuditLogEntryView)
        assert isinstance(entries[0].id, uuid.UUID)
        assert entries[0].action == "clan.suspend"
        assert entries[0].clan_id == clan_id


async def test_platform_admin_handler_preserves_wire_contract(
    async_engine: AsyncEngine,
) -> None:
    """The handler re-serializes the typed views into the SAME wire shape the API
    emitted before L4 (string ids, nested meta) — so the client contract is unchanged.
    Also proves the nullability fix: a NULL clan_id audit row serializes to JSON null,
    not the literal string ``"None"`` the old ``str(e.clan_id)`` produced."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, actor_id = uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        await _clan(s, clan_id)
        await _profile(s, actor_id)
        await _audit(s, clan_id, actor_id, "clan.suspend")
        await _audit(s, None, actor_id, "platform.login")  # platform-level: clan_id NULL
        await s.commit()

        handler = PlatformAdminQueryHandler(SqlAlchemyPlatformAdminQueryPort(s))

        detail = await handler.get_clan_detail(clan_id=clan_id)
        assert detail["id"] == str(clan_id)  # wire id is a string
        assert set(detail) >= {"id", "name", "slug", "is_active", "stats", "created_at"}
        assert set(detail["stats"]) == {"total_members", "total_users"}

        clans = await handler.list_clans(cursor=None, limit=20)
        assert set(clans) == {"data", "meta"}
        assert set(clans["meta"]) == {"cursor", "has_more", "limit"}
        assert all(isinstance(c["id"], str) for c in clans["data"])

        # Two deterministic, scoped queries instead of one global (clan_id=None)
        # query -- the global query's ASC (created_at, id) pagination window
        # would otherwise miss this test's own rows once the session-scoped
        # DB accumulates >= `limit` audit_log rows from earlier-run tests.
        clan_log = await handler.get_audit_log(clan_id=clan_id, action=None, cursor=None, limit=20)
        clan_by_action = {
            e["action"]: e for e in clan_log["data"] if e["actor_id"] == str(actor_id)
        }
        assert clan_by_action["clan.suspend"]["clan_id"] == str(clan_id)

        platform_log = await handler.get_audit_log(
            clan_id=None, action="platform.login", cursor=None, limit=20
        )
        platform_by_action = {
            e["action"]: e for e in platform_log["data"] if e["actor_id"] == str(actor_id)
        }
        assert platform_by_action["platform.login"]["clan_id"] is None  # NOT the string "None"

        metrics = await handler.get_metrics()
        assert set(metrics) == {
            "total_clans",
            "active_clans",
            "suspended_clans",
            "total_members",
            "total_users",
        }
        assert all(isinstance(v, int) for v in metrics.values())

        # Coherence: the documentation-only OpenAPI response schemas must accept the
        # real handler wire dicts, or a schema/handler drift ships silently to codegen.
        from app.schemas.platform_admin import (
            AuditLogEntryResponse,
            ClanDetailResponse,
            ClanSummaryResponse,
            PlatformMetricsResponse,
        )

        ClanDetailResponse.model_validate(detail)
        for c in clans["data"]:
            ClanSummaryResponse.model_validate(c)
        PlatformMetricsResponse.model_validate(metrics)
        for e in clan_log["data"]:
            AuditLogEntryResponse.model_validate(e)
        for e in platform_log["data"]:
            AuditLogEntryResponse.model_validate(e)  # clan_id is None here — must validate


async def test_platform_admin_audit_log_paginates_across_cursor(
    async_engine: AsyncEngine,
) -> None:
    """Exercise the one genuinely new control flow: the cursor is computed from the
    ORM rows (via build_page) while the page data is mapped to typed views. Scoped
    to a fresh clan_id so it is deterministic despite the session-scoped DB."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, actor_id = uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        await _clan(s, clan_id)
        await _profile(s, actor_id)
        for i in range(3):
            await _audit(s, clan_id, actor_id, f"clan.act{i}")
        await s.commit()

        port = SqlAlchemyPlatformAdminQueryPort(s)

        page1 = await port.get_audit_log(clan_id, None, None, 2)
        assert len(page1.data) == 2
        assert page1.meta.has_more is True
        assert page1.meta.cursor is not None  # cursor derived from the ORM row
        assert all(isinstance(e, AuditLogEntryView) for e in page1.data)

        page2 = await port.get_audit_log(clan_id, None, page1.meta.cursor, 2)
        assert len(page2.data) == 1  # the remaining row
        assert page2.meta.has_more is False
        # the cursor genuinely advanced — no row appears on both pages
        assert not ({e.id for e in page1.data} & {e.id for e in page2.data})


async def test_clan_update_through_aggregate_persists_and_audits(
    async_engine: AsyncEngine,
) -> None:
    """L12: clan updates flow through the Clan aggregate — the change persists, a
    clan.update audit row is written, and a non-whitelisted field is rejected at the
    domain (defense-in-depth beyond the request schema) without touching the DB."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, admin_id = uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        await _clan(s, clan_id)
        await s.commit()

        handler = ClanCommandHandler(
            # list_users return type differs from the port (a known pre-existing Minor
            # mismatch, see the platform_admin test above) — not exercised here.
            SqlAlchemyClanRepository(s),  # type: ignore[arg-type]
            SqlAlchemyUnitOfWork(s, create_event_dispatcher(s)),
        )
        actor = ActorInfo.from_jwt({"sub": str(admin_id)}, "admin")

        await handler.update_clan(
            UpdateClan(
                clan_id=clan_id, actor=actor, changes={"name": "Nguyễn Tộc", "motto": "Kính tổ"}
            )
        )

        name = await s.scalar(sa.text("SELECT name FROM clans WHERE id = :c"), {"c": clan_id})
        assert name == "Nguyễn Tộc"
        audit_rows = (
            await s.execute(
                sa.text(
                    "SELECT new_value FROM audit_logs WHERE clan_id = :c AND action = 'clan.update'"
                ),
                {"c": clan_id},
            )
        ).all()
        assert len(audit_rows) == 1
        # the audit trail records WHAT changed (not just that an update happened)
        assert audit_rows[0][0] == {"name": "Nguyễn Tộc", "motto": "Kính tổ"}

        # A field outside the whitelist is refused by the aggregate — the request
        # schema has no such field, so this is the domain-level backstop.
        with pytest.raises(BusinessRuleViolation, match="field_not_updatable"):
            await handler.update_clan(
                UpdateClan(clan_id=clan_id, actor=actor, changes={"is_active": False})
            )
        still_active = await s.scalar(
            sa.text("SELECT is_active FROM clans WHERE id = :c"), {"c": clan_id}
        )
        assert still_active is True  # the rejected write never reached the DB


async def test_platform_admin_suspend_and_reactivate(async_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, admin_id = uuid.uuid4(), uuid.uuid4()

    async with maker() as s:
        await _clan(s, clan_id)
        await s.commit()

        async def _is_active() -> bool:
            return bool(
                await s.scalar(sa.text("SELECT is_active FROM clans WHERE id = :c"), {"c": clan_id})
            )

        async def _audit_count() -> int:
            sql = "SELECT count(*) FROM audit_logs WHERE clan_id = :c AND resource_type = 'clan'"
            return (await s.execute(sa.text(sql), {"c": clan_id})).scalar() or 0

        actor = ActorInfo.from_jwt({"sub": str(admin_id)}, "admin")
        # SqlAlchemyClanRepository satisfies what PlatformAdminCommandHandler uses
        # (load + mutate clan); its list_users return type differs from the port
        # (a known Minor mismatch) — not exercised here.
        handler = PlatformAdminCommandHandler(
            SqlAlchemyClanRepository(s),  # type: ignore[arg-type]
            SqlAlchemyUnitOfWork(s, create_event_dispatcher(s)),
        )

        assert await _is_active() is True
        await handler.suspend_clan(clan_id=clan_id, actor=actor)
        assert await _is_active() is False  # suspension flips the flag
        await handler.reactivate_clan(clan_id=clan_id, actor=actor)
        assert await _is_active() is True
        assert await _audit_count() >= 2  # suspend + reactivate both audited
