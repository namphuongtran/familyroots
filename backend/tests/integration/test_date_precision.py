"""RED (Task 1 of the M4+M5 date-precision-correctness plan).

M4: a RECURRING giỗ/birthday event whose date is only an ESTIMATE
(``event_date_precision`` in {year, month, circa, unknown}, not 'exact') must not
fire a fabricated-anniversary FCM push, and must not appear in ``/events/upcoming``
— today neither the scheduler's SQL (``app/services/scheduler.py``) nor
``SqlAlchemyEventRepository.get_upcoming`` looks at ``event_date_precision`` at all,
so estimated recurring dates notify/appear exactly like exact ones. The gate is
RECURRING-scoped only: a one-off event is unaffected (its date is real, just
precision-tagged) and must keep appearing — that is the control test in this file.

M5: ``RelationshipDomainValidator.validate_parent_child`` hard-blocks
``relationship.parent_too_young`` off ``get_birth_dates``, which returns bare
``date | None`` with no precision — so today the floor is enforced identically
whether a birth date is 'exact' or an admittedly uncertain 'circa'/'year' estimate.
Task 2 must downgrade the block to an advisory ``meta.warning`` when either date is
non-exact, WITHOUT skipping cycle detection.

Task 2 (not this task) fixes both. This file only proves today's behavior and pins
the desired post-fix behavior; per-test RED/GREEN outcomes are recorded in
``.superpowers/sdd/task-1-report.md``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.database  # noqa: F401
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.event_repository import SqlAlchemyEventRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.main import create_app
from app.services import scheduler

pytestmark = pytest.mark.integration


def _platform_today() -> date:
    """Mirrors test_scheduler_robustness.py: the scheduler computes "today" in the
    platform timezone (Asia/Ho_Chi_Minh); a UTC CI runner late in the day is a
    calendar day BEHIND the platform, so seeding with date.today() can put "due in
    N days" events one platform-day off from what the job actually computes."""
    return datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE)).date()


# ── M4: recurring events at a non-exact date precision ───────────────────────


@pytest.fixture()
async def async_engine(migrated_db_url: str) -> AsyncGenerator[Any]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


async def _seed_recurring_event(
    maker: async_sessionmaker[AsyncSession],
    *,
    precision: str,
    lunar: bool = False,
) -> uuid.UUID:
    """One recurring giỗ event positioned at the scheduler's notify boundary
    (event_date = platform-today + 7d, notify_days_before=7 — the same boundary
    mechanics as test_scheduler_robustness.py's ``_seed_event``), plus a live
    (non-deleted) person, with an explicit ``event_date_precision``."""
    clan_id, person_id = uuid.uuid4(), uuid.uuid4()
    event_date = _platform_today() + timedelta(days=7)
    async with maker() as s:
        await s.execute(sa.text("DELETE FROM notification_log"))
        await s.execute(sa.text("DELETE FROM events"))
        await s.commit()
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:i,'C',:sg)"),
            {"i": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, created_by, is_deleted) "
                "VALUES (:i, 'P', :cb, false)"
            ),
            {"i": person_id, "cb": uuid.uuid4()},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events (id, clan_id, event_type, title, event_date, "
                "event_date_precision, is_recurring, is_lunar_calendar, "
                "notify_days_before, person_id, created_by) "
                "VALUES (:i,:c,'death_anniversary','Giỗ',:d,:prec,true,:lu,7,:p,:cb)"
            ),
            {
                "i": uuid.uuid4(),
                "c": clan_id,
                "d": event_date,
                "prec": precision,
                "lu": lunar,
                "p": person_id,
                "cb": uuid.uuid4(),
            },
        )
        await s.commit()
    return clan_id


async def _seed_oneoff_event(
    maker: async_sessionmaker[AsyncSession], *, precision: str
) -> uuid.UUID:
    """One NON-recurring future event with an explicit precision — used to pin
    that the M4 recurring-precision gate must not over-filter one-offs."""
    clan_id = uuid.uuid4()
    event_date = _platform_today() + timedelta(days=10)
    async with maker() as s:
        await s.execute(sa.text("DELETE FROM notification_log"))
        await s.execute(sa.text("DELETE FROM events"))
        await s.commit()
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:i,'C',:sg)"),
            {"i": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events (id, clan_id, event_type, title, event_date, "
                "event_date_precision, is_recurring, is_lunar_calendar, "
                "notify_days_before, created_by) "
                "VALUES (:i,:c,'birthday','OneOff',:d,:prec,false,false,7,:cb)"
            ),
            {
                "i": uuid.uuid4(),
                "c": clan_id,
                "d": event_date,
                "prec": precision,
                "cb": uuid.uuid4(),
            },
        )
        await s.commit()
    return clan_id


async def _upcoming_titles(
    maker: async_sessionmaker[AsyncSession], clan_id: uuid.UUID, today: date
) -> set[str]:
    async with maker() as s:
        repo = SqlAlchemyEventRepository(SqlAlchemyUnitOfWork(s, create_event_dispatcher(s)))
        rows = await repo.get_upcoming(
            clan_id, today=today, end_date=today + timedelta(days=30), limit=50
        )
    return {r["title"] for r in rows}


async def test_recurring_circa_event_is_not_notified_and_not_in_upcoming(
    async_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M4 RED: a recurring solar giỗ dated only 'circa' (best-guess death date)
    must not fire a fabricated-anniversary FCM push and must not appear in
    /events/upcoming. TODAY: neither query filters on event_date_precision, so
    the scheduler DOES send (spy.await_count == 1) and the event DOES appear in
    upcoming — both assertions below fail today."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)
    clan_id = await _seed_recurring_event(maker, precision="circa")

    await scheduler.send_anniversary_notifications()
    assert spy.await_count == 0  # RED today: observed 1 (it fires)

    titles = await _upcoming_titles(maker, clan_id, _platform_today())
    assert "Giỗ" not in titles  # RED today: observed present


async def test_recurring_exact_event_notifies_and_appears(
    async_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive control (GREEN today and after Task 2): identical seeding but
    precision='exact' — a real, precisely-known date must keep notifying and
    keep appearing in /upcoming."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)
    clan_id = await _seed_recurring_event(maker, precision="exact")

    await scheduler.send_anniversary_notifications()
    assert spy.await_count == 1

    titles = await _upcoming_titles(maker, clan_id, _platform_today())
    assert "Giỗ" in titles


async def test_recurring_lunar_circa_excluded(
    async_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M4 RED, lunar variant: is_lunar_calendar=true + precision='circa' recurring
    event must not be notified and must not appear in upcoming. TODAY: the lunar
    branch of both the scheduler and get_upcoming also ignores
    event_date_precision, so this notifies/appears just like the solar circa case
    (test_lunar_event_is_included in test_scheduler_robustness.py proves this exact
    seeding shape already notifies for a lunar event with no precision filter)."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)
    clan_id = await _seed_recurring_event(maker, precision="circa", lunar=True)

    await scheduler.send_anniversary_notifications()
    assert spy.await_count == 0  # RED today: observed 1 (it fires)

    titles = await _upcoming_titles(maker, clan_id, _platform_today())
    assert "Giỗ" not in titles  # RED today: observed present


async def test_oneoff_circa_future_event_still_in_upcoming(async_engine: Any) -> None:
    """Control (GREEN today AND after Task 2): M4's precision gate is
    RECURRING-scoped. A one-off (is_recurring=false) circa-precision future event
    is not a fabricated anniversary — it is a real future date whose precision is
    merely uncertain — so it must keep appearing in /upcoming. Pins that the fix
    must not over-filter one-offs."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    clan_id = await _seed_oneoff_event(maker, precision="circa")

    titles = await _upcoming_titles(maker, clan_id, _platform_today())
    assert "OneOff" in titles


# ── M5: parent_too_young must respect birth-date precision ───────────────────


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


@pytest.fixture()
async def session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


@pytest.fixture()
async def seeded(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """A clan plus an approved editor membership."""
    clan_id = uuid.uuid4()
    editor_id = uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO clans (id, name, slug) VALUES (:id, 'Date Precision Clan', :slug)"
            ),
            {"id": clan_id, "slug": f"dateprec-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :email, :name)"
            ),
            {"id": editor_id, "email": f"{editor_id.hex[:8]}@example.com", "name": "editor"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:uid, :cid, 'editor', true, :uid, now())"
            ),
            {"uid": editor_id, "cid": clan_id},
        )
        await s.commit()
    return {"clan_id": clan_id, "editor_id": editor_id}


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture()
def editor_headers(seeded: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {seeded['editor_id']}",
        "X-Current-Clan-Id": str(seeded["clan_id"]),
    }


async def _make_person(
    client: AsyncClient,
    headers: dict[str, str],
    name: str,
    birth_date: date,
    *,
    precision: str = "exact",
) -> str:
    resp = await client.post(
        "/api/v1/persons",
        headers=headers,
        json={
            "full_name": name,
            "birth_date": birth_date.isoformat(),
            "birth_date_precision": precision,
        },
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


async def test_parent_too_young_hard_when_both_birth_dates_exact(
    client: AsyncClient, editor_headers: dict[str, str]
) -> None:
    """Regression pin (control, GREEN today and after Task 2): both birth dates
    'exact', 5y gap < the 12y biological floor → hard 422
    relationship.parent_too_young. Precision-awareness must not weaken the floor
    when both dates really are exact."""
    child = await _make_person(client, editor_headers, "Child M5-A", date(2015, 1, 1))
    parent = await _make_person(client, editor_headers, "Parent M5-A", date(2010, 1, 1))
    resp = await client.post(
        "/api/v1/relationships/parent-child",
        headers=editor_headers,
        json={"parent_id": parent, "child_id": child, "relationship_type": "biological"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "relationship.parent_too_young"


async def test_parent_too_young_downgraded_to_warning_when_nonexact(
    client: AsyncClient, editor_headers: dict[str, str]
) -> None:
    """M5 RED: same 5y gap, but the PARENT's birth date is only 'circa' (an
    estimate). Task 2 must downgrade the hard block to an advisory warning — edge
    CREATED (201, not 422), with meta.warning set — because hard-blocking on an
    admittedly uncertain date is the bug. TODAY: validate_parent_child's
    get_birth_dates returns bare ``date | None`` with no precision column at all,
    so precision is invisible to the age check and this still hard-422s — RED
    (observed 422, not the desired 201 + meta.warning)."""
    child = await _make_person(client, editor_headers, "Child M5-B", date(2015, 1, 1))
    parent = await _make_person(
        client, editor_headers, "Parent M5-B", date(2010, 1, 1), precision="circa"
    )
    resp = await client.post(
        "/api/v1/relationships/parent-child",
        headers=editor_headers,
        json={"parent_id": parent, "child_id": child, "relationship_type": "biological"},
    )
    assert resp.status_code == 201, resp.text  # RED today: 422 parent_too_young
    assert resp.json()["meta"]["warning"]  # RED today: no meta (never reached)


async def test_cycle_still_detected_when_age_downgraded_to_warning(
    client: AsyncClient, editor_headers: dict[str, str]
) -> None:
    """M5: proves the future age-warning downgrade does NOT short-circuit before
    cycle detection. A (born 1970, precision='circa') is made parent-of B (born
    2000, exact) first — a clean 30y gap, no age issue, succeeds normally. Then B
    is attempted as parent-of A: this both reverses an existing edge (would close
    a 2-node cycle) AND produces a negative/<12y age gap on a non-exact date (A's
    birth date is 'circa'). Once Task 2 downgrades that age check to a warning
    instead of hard-blocking, cycle detection must still run and reject with
    `relationship.creates_cycle` — proving the warning path does not early-return
    before the cycle check.

    Both parent_too_young and creates_cycle are `BusinessRuleViolation` → HTTP
    **422**; the discriminator that proves the fix is the error CODE, not the
    status. TODAY-STATE: validate_parent_child runs the hard parent_too_young
    check BEFORE the cycle check, so today this second POST fails 422
    `relationship.parent_too_young` and never reaches is_ancestor. Once Task 2
    downgrades the age check to a warning for the non-exact date AND keeps cycle
    detection after it, the same 422 carries code `relationship.creates_cycle`
    instead — which is what this test asserts.
    """
    a = await _make_person(client, editor_headers, "A M5-C", date(1970, 1, 1), precision="circa")
    b = await _make_person(client, editor_headers, "B M5-C", date(2000, 1, 1))

    ok = await client.post(
        "/api/v1/relationships/parent-child",
        headers=editor_headers,
        json={"parent_id": a, "child_id": b, "relationship_type": "biological"},
    )
    assert ok.status_code == 201, ok.text

    cycle_attempt = await client.post(
        "/api/v1/relationships/parent-child",
        headers=editor_headers,
        json={"parent_id": b, "child_id": a, "relationship_type": "biological"},
    )
    assert cycle_attempt.status_code == 422, cycle_attempt.text
    # The CODE is the discriminator: today it's parent_too_young (hard age check
    # fires first); after the fix it's creates_cycle (age downgraded to a warning,
    # cycle check still runs).
    assert cycle_attempt.json()["error"]["code"] == "relationship.creates_cycle"


async def test_adoptive_under_12_still_allowed(
    client: AsyncClient, editor_headers: dict[str, str]
) -> None:
    """Control (GREEN today and after Task 2): the >=12y floor is a
    BIOLOGICAL-only rule — an adoptive parent may be any age (e.g. an older
    sibling adopting) regardless of date precision. A 5y gap with a non-exact
    parent birth date must still succeed."""
    child = await _make_person(client, editor_headers, "Child M5-D", date(2015, 1, 1))
    parent = await _make_person(
        client, editor_headers, "Parent M5-D", date(2010, 1, 1), precision="circa"
    )
    resp = await client.post(
        "/api/v1/relationships/parent-child",
        headers=editor_headers,
        json={"parent_id": parent, "child_id": child, "relationship_type": "adopted"},
    )
    assert resp.status_code == 201, resp.text
