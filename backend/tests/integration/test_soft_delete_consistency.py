"""Real-DB tests PROVING review finding M3: five write guards accept soft-deleted
persons as valid references (marriage, parent-child, event, document, branch
founder — both the create AND update sites), and ``/events/upcoming`` leaks a
soft-deleted person's giỗ (their event id AND their name) while the anniversary
scheduler already correctly suppresses the same person — so the two consumers of
"is this person's giỗ due" disagree.

Task 2 (NOT this file) fixes the guards. This file only proves the hole:
every "blocked-path" assertion below is written for the DESIRED behavior and is
EXPECTED TO FAIL today (the create/upload/update currently SUCCEEDS against a
soft-deleted person). Each test also carries a restore-symmetry POSITIVE
control — proving the create/upload/update path works normally for a person who
was soft-deleted and then restored — asserted BEFORE the blocked-path assertion
so it always executes and is verifiably true today, independent of whether the
blocked-path assertion (deliberately, today) aborts the test.

Where a surface has a duplicate-relationship business rule (marriage,
parent-child), the control uses an INDEPENDENT pair of persons rather than
reusing the blocked pair — reusing the same pair would hit that rule's
ConflictError today (the blocked create already silently succeeded and created
the row), which is a false signal unrelated to M3.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import date, timedelta
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.database  # noqa: F401  (ensures the module is loaded before monkeypatch)
from app.application.branch.handlers import BranchCommandHandler
from app.application.document.handlers import DocumentCommandHandler
from app.application.event.handlers import EventCommandHandler, EventQueryHandler
from app.application.person.claim_handlers import ClaimCommandHandler
from app.application.relationship.commands import CreateMarriage, CreateParentChild
from app.application.relationship.handlers import (
    MarriageCommandHandler,
    ParentChildCommandHandler,
)
from app.core.config import settings
from app.domain.relationship.validator import RelationshipDomainValidator
from app.domain.shared.exceptions import EntityNotFoundError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.branch_repository import SqlAlchemyBranchRepository
from app.infrastructure.persistence.claim_repository import SqlAlchemyClaimRepository
from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
from app.infrastructure.persistence.event_repository import SqlAlchemyEventRepository
from app.infrastructure.persistence.relationship_repository import (
    SqlAlchemyMarriageRepository,
    SqlAlchemyParentChildRepository,
    SqlAlchemyRelationshipQueryPort,
)
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.services import scheduler

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


# ── Seed helpers (mirror tests/integration/test_doi_authority.py) ──────────


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _clan(s: AsyncSession) -> uuid.UUID:
    cid = uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": cid, "s": f"c{cid.hex[:8]}"},
    )
    return cid


async def _person(
    s: AsyncSession,
    clan_id: uuid.UUID,
    creator: uuid.UUID,
    name: str = "P",
    *,
    gender: str = "male",
) -> uuid.UUID:
    pid = uuid.uuid4()
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, :n, :g, :c, :cb)"
        ),
        {"id": pid, "n": name, "g": gender, "c": clan_id, "cb": creator},
    )
    return pid


async def _member(s: AsyncSession, person_id: uuid.UUID, clan_id: uuid.UUID) -> None:
    await s.execute(
        sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
        {"p": person_id, "c": clan_id},
    )


async def _set_deleted(s: AsyncSession, person_id: uuid.UUID, deleted: bool) -> None:
    """Raw soft-delete/restore toggle — the schema requires deleted_at alongside
    is_deleted (see app/models/person.py)."""
    await s.execute(
        sa.text(
            "UPDATE persons SET is_deleted = :d, "
            "deleted_at = CASE WHEN :d THEN now() ELSE NULL END WHERE id = :p"
        ),
        {"d": deleted, "p": person_id},
    )
    await s.commit()


class FakeStorage:
    """In-memory StoragePort double (mirrors tests/integration/test_document_soft_delete.py)
    — records uploads so the blocked path can assert no blob was ever written."""

    def __init__(self) -> None:
        self.uploaded: list[str] = []

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        self.uploaded.append(path)
        return path

    async def delete(self, storage_path: str) -> bool:
        return True

    async def get_presigned_url(self, storage_path: str, expires_in: int = 3600) -> str:
        return f"https://signed.example/{storage_path}"


def _platform_today() -> date:
    """Same rationale as tests/integration/test_scheduler_robustness.py: the
    scheduler computes "today" in the platform timezone, so seeding relative to
    a UTC date.today() can be a calendar day off near midnight UTC."""
    from datetime import datetime

    return datetime.now(ZoneInfo(settings.SCHEDULER_TIMEZONE)).date()


# ── Marriage ─────────────────────────────────────────────────────────────


async def test_marriage_creation_blocked_for_soft_deleted_person(
    async_session: AsyncSession,
) -> None:
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    uow = SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    validator = RelationshipDomainValidator(SqlAlchemyRelationshipQueryPort(async_session))
    handler = MarriageCommandHandler(SqlAlchemyMarriageRepository(uow), uow, validator)
    actor = ActorInfo(user_id=creator, role="editor")

    # Restore-symmetry control (independent pair — a duplicate-marriage
    # ConflictError would give a false signal if this reused the blocked pair,
    # since the blocked create below currently succeeds and creates a row).
    h_ctrl = await _person(async_session, clan_id, creator, "H-ctrl")
    w_ctrl = await _person(async_session, clan_id, creator, "W-ctrl", gender="female")
    await _member(async_session, h_ctrl, clan_id)
    await _member(async_session, w_ctrl, clan_id)
    await async_session.commit()
    await _set_deleted(async_session, w_ctrl, True)
    await _set_deleted(async_session, w_ctrl, False)  # restored before use

    ctrl = await handler.create(
        CreateMarriage(person1_id=h_ctrl, person2_id=w_ctrl, clan_id=clan_id, actor=actor)
    )
    assert ctrl.person1_id == h_ctrl and ctrl.person2_id == w_ctrl

    # Blocked path: live H + currently soft-deleted W.
    h = await _person(async_session, clan_id, creator, "H")
    w = await _person(async_session, clan_id, creator, "W", gender="female")
    await _member(async_session, h, clan_id)
    await _member(async_session, w, clan_id)
    await async_session.commit()
    await _set_deleted(async_session, w, True)

    with pytest.raises(EntityNotFoundError, match="person_not_found"):
        await handler.create(
            CreateMarriage(person1_id=h, person2_id=w, clan_id=clan_id, actor=actor)
        )


# ── Parent-child ─────────────────────────────────────────────────────────


async def test_parent_child_creation_blocked_for_soft_deleted_person(
    async_session: AsyncSession,
) -> None:
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    uow = SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    validator = RelationshipDomainValidator(SqlAlchemyRelationshipQueryPort(async_session))
    handler = ParentChildCommandHandler(SqlAlchemyParentChildRepository(uow), uow, validator)
    actor = ActorInfo(user_id=creator, role="editor")

    # Restore-symmetry control (independent pair — same duplicate-edge rationale
    # as the marriage test above).
    parent_ctrl = await _person(async_session, clan_id, creator, "Parent-ctrl")
    child_ctrl = await _person(async_session, clan_id, creator, "Child-ctrl")
    await _member(async_session, parent_ctrl, clan_id)
    await _member(async_session, child_ctrl, clan_id)
    await async_session.commit()
    await _set_deleted(async_session, parent_ctrl, True)
    await _set_deleted(async_session, parent_ctrl, False)

    ctrl_link, _warning = await handler.create(
        CreateParentChild(parent_id=parent_ctrl, child_id=child_ctrl, clan_id=clan_id, actor=actor)
    )
    assert ctrl_link.parent_id == parent_ctrl and ctrl_link.child_id == child_ctrl

    # Blocked path: soft-deleted parent.
    parent = await _person(async_session, clan_id, creator, "Parent")
    child = await _person(async_session, clan_id, creator, "Child")
    await _member(async_session, parent, clan_id)
    await _member(async_session, child, clan_id)
    await async_session.commit()
    await _set_deleted(async_session, parent, True)

    with pytest.raises(EntityNotFoundError, match="person_not_found"):
        await handler.create(
            CreateParentChild(parent_id=parent, child_id=child, clan_id=clan_id, actor=actor)
        )


# ── Event ────────────────────────────────────────────────────────────────


async def test_event_creation_blocked_for_soft_deleted_person(
    async_session: AsyncSession,
) -> None:
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    uow = SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    handler = EventCommandHandler(SqlAlchemyEventRepository(uow), uow)
    actor = ActorInfo(user_id=creator, role="editor")

    def _kwargs(person_id: uuid.UUID) -> dict[str, Any]:
        return {
            "clan_id": clan_id,
            "actor": actor,
            "person_id": person_id,
            "event_type": "death_anniversary",
            "title": "Giỗ",
            "description": None,
            "event_date": date(2020, 1, 1),
            "is_lunar_calendar": False,
            "is_recurring": True,
            "notify_days_before": 7,
        }

    # Restore-symmetry control: same person, deleted then restored before use —
    # no duplicate-edge rule applies to events, so reusing one person is safe.
    person_ctrl = await _person(async_session, clan_id, creator, "Ctrl")
    await _member(async_session, person_ctrl, clan_id)
    await async_session.commit()
    await _set_deleted(async_session, person_ctrl, True)
    await _set_deleted(async_session, person_ctrl, False)

    ctrl = await handler.create(**_kwargs(person_ctrl))
    assert ctrl.person_id == person_ctrl

    # Blocked path.
    person = await _person(async_session, clan_id, creator, "Deleted")
    await _member(async_session, person, clan_id)
    await async_session.commit()
    await _set_deleted(async_session, person, True)

    with pytest.raises(EntityNotFoundError, match="person_not_found"):
        await handler.create(**_kwargs(person))


# ── Document ─────────────────────────────────────────────────────────────


async def test_document_upload_blocked_for_soft_deleted_person(
    async_session: AsyncSession,
) -> None:
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    storage = FakeStorage()
    uow = SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    handler = DocumentCommandHandler(SqlAlchemyDocumentRepository(uow), storage, uow)
    actor = ActorInfo(user_id=creator, role="editor")

    # Restore-symmetry control.
    person_ctrl = await _person(async_session, clan_id, creator, "Ctrl")
    await _member(async_session, person_ctrl, clan_id)
    await async_session.commit()
    await _set_deleted(async_session, person_ctrl, True)
    await _set_deleted(async_session, person_ctrl, False)

    ctrl = await handler.upload(
        file_content=_PNG_BYTES,
        filename="ctrl.png",
        content_type="image/png",
        title="Ctrl doc",
        document_type="photo",
        clan_id=clan_id,
        actor=actor,
        person_id=person_ctrl,
    )
    assert ctrl.person_id == person_ctrl
    assert storage.uploaded  # sanity: the control path really uploads

    # Blocked path: no orphan blob must land in storage.
    person = await _person(async_session, clan_id, creator, "Deleted")
    await _member(async_session, person, clan_id)
    await async_session.commit()
    await _set_deleted(async_session, person, True)

    uploaded_before = list(storage.uploaded)
    with pytest.raises(EntityNotFoundError, match="person_not_found"):
        await handler.upload(
            file_content=_PNG_BYTES,
            filename="blocked.png",
            content_type="image/png",
            title="Blocked doc",
            document_type="photo",
            clan_id=clan_id,
            actor=actor,
            person_id=person,
        )
    assert storage.uploaded == uploaded_before, (
        "M3: a blocked upload must not touch storage (no orphan blob)"
    )


# ── Branch founder (both guard sites: create + update) ──────────────────


async def test_branch_founder_blocked_for_soft_deleted_person(
    async_session: AsyncSession,
) -> None:
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    uow = SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    handler = BranchCommandHandler(SqlAlchemyBranchRepository(uow), uow)
    actor = ActorInfo(user_id=creator, role="editor")

    founder_ctrl = await _person(async_session, clan_id, creator, "Founder-ctrl")
    founder_blocked = await _person(async_session, clan_id, creator, "Founder-blocked")
    await _member(async_session, founder_ctrl, clan_id)
    await _member(async_session, founder_blocked, clan_id)
    await async_session.commit()
    await _set_deleted(async_session, founder_ctrl, True)
    await _set_deleted(async_session, founder_ctrl, False)  # restored before use
    await _set_deleted(async_session, founder_blocked, True)  # stays deleted

    # Restore-symmetry controls for BOTH guard sites — asserted first, so they
    # always run regardless of what the blocked-path checks below do.
    ctrl_branch = await handler.create(
        clan_id=clan_id, actor=actor, name="Ctrl Branch", founder_person_id=founder_ctrl
    )
    assert ctrl_branch.founder_person_id == founder_ctrl  # create-site control (handlers.py:44)

    update_target = await handler.create(clan_id=clan_id, actor=actor, name="Update Target")
    updated_ctrl = await handler.update(
        branch_id=update_target.id,
        clan_id=clan_id,
        actor=actor,
        changes={"founder_person_id": founder_ctrl},
    )
    assert updated_ctrl.founder_person_id == founder_ctrl  # update-site control (handlers.py:93)

    # Blocked paths for BOTH sites — captured via try/except (not pytest.raises)
    # so both are actually attempted this run regardless of which one aborts
    # the test first via a failing assert below.
    create_blocked_exc: EntityNotFoundError | None = None
    try:
        await handler.create(
            clan_id=clan_id, actor=actor, name="Blocked Branch", founder_person_id=founder_blocked
        )
    except EntityNotFoundError as exc:
        create_blocked_exc = exc

    update_blocked_exc: EntityNotFoundError | None = None
    try:
        await handler.update(
            branch_id=update_target.id,
            clan_id=clan_id,
            actor=actor,
            changes={"founder_person_id": founder_blocked},
        )
    except EntityNotFoundError as exc:
        update_blocked_exc = exc

    assert create_blocked_exc is not None and create_blocked_exc.code == "person_not_found", (
        "M3: branch CREATE accepted a soft-deleted founder_person_id (handlers.py:44)"
    )
    assert update_blocked_exc is not None and update_blocked_exc.code == "person_not_found", (
        "M3: branch UPDATE accepted a soft-deleted founder_person_id (handlers.py:93)"
    )


# ── /events/upcoming leak + scheduler parity ─────────────────────────────


@pytest.fixture()
async def scheduler_engine(migrated_db_url: str) -> AsyncGenerator[Any]:
    engine = create_async_engine(migrated_db_url)
    yield engine
    await engine.dispose()


async def test_upcoming_hides_deleted_persons_gio_and_matches_scheduler(
    scheduler_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    maker = async_sessionmaker(scheduler_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", scheduler_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    monkeypatch.setattr("app.services.notification.send_to_clan", AsyncMock(return_value=(1, 0)))

    today = _platform_today()
    event_date = today + timedelta(days=7)
    clan_id = uuid.uuid4()
    x_id, y_id = uuid.uuid4(), uuid.uuid4()
    x_event_id, y_event_id, z_event_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    x_name = "Nguyen Thi X Deleted"
    y_name = "Nguyen Van Y Live"

    async with maker() as s:
        # Scheduler has no clan scope (by design) — wipe first, matching the
        # established pattern in test_scheduler_robustness.py, so leftover rows
        # from other tests can't pollute this run's notification_log.
        await s.execute(sa.text("DELETE FROM notification_log"))
        await s.execute(sa.text("DELETE FROM events"))
        await s.commit()
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:i, 'C', :sg)"),
            {"i": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        for pid, name in [(x_id, x_name), (y_id, y_name)]:
            await s.execute(
                sa.text("INSERT INTO persons (id, full_name, created_by) VALUES (:i, :n, :cb)"),
                {"i": pid, "n": name, "cb": uuid.uuid4()},
            )
        event_person_pairs: list[tuple[uuid.UUID, uuid.UUID | None]] = [
            (x_event_id, x_id),
            (y_event_id, y_id),
            (z_event_id, None),
        ]
        for eid, linked_person_id in event_person_pairs:
            await s.execute(
                sa.text(
                    "INSERT INTO events (id, clan_id, event_type, title, event_date, "
                    "is_recurring, is_lunar_calendar, notify_days_before, person_id, created_by) "
                    "VALUES (:i, :c, 'death_anniversary', 'Giỗ', :d, true, false, 7, :p, :cb)"
                ),
                {
                    "i": eid,
                    "c": clan_id,
                    "d": event_date,
                    "p": linked_person_id,
                    "cb": uuid.uuid4(),
                },
            )
        await s.commit()

    async with maker() as s:
        await _set_deleted(s, x_id, True)

    async with maker() as s:
        repo = SqlAlchemyEventRepository(SqlAlchemyUnitOfWork(s, create_event_dispatcher(s)))
        handler = EventQueryHandler(repo)
        upcoming = await handler.get_upcoming(clan_id=clan_id, days=30, today=today)
    upcoming_ids = {item["id"] for item in upcoming}
    payload_str = json.dumps(upcoming, default=str)

    # Scheduler-parity: run the SAME job real code paths use, then read back
    # which of our three events it actually logged/attempted to notify for.
    await scheduler.send_anniversary_notifications(today=today)
    async with maker() as s:
        rows = (
            await s.execute(
                sa.text("SELECT DISTINCT event_id FROM notification_log WHERE sent_on = :today"),
                {"today": today},
            )
        ).all()
    scheduler_ids = {str(r[0]) for r in rows}

    # Restore X and re-check.
    async with maker() as s:
        await s.execute(
            sa.text("UPDATE persons SET is_deleted = false, deleted_at = NULL WHERE id = :p"),
            {"p": x_id},
        )
        await s.commit()
    async with maker() as s:
        repo2 = SqlAlchemyEventRepository(SqlAlchemyUnitOfWork(s, create_event_dispatcher(s)))
        handler2 = EventQueryHandler(repo2)
        upcoming_after_restore = await handler2.get_upcoming(clan_id=clan_id, days=30, today=today)
    ids_after_restore = {item["id"] for item in upcoming_after_restore}

    # ---- Controls: pass today AND after the fix ----
    assert str(y_event_id) in upcoming_ids  # live Y's giỗ is present
    assert str(z_event_id) in upcoming_ids  # person-less clan ceremony is present
    assert str(x_event_id) in ids_after_restore  # restore-symmetry: X's giỗ reappears

    # ---- M3 leak — FAIL today (creates/handlers.py fix is Task 2, not here) ----
    assert str(x_event_id) not in upcoming_ids, (
        "M3: /events/upcoming leaks a soft-deleted person's giỗ event id"
    )
    assert x_name not in payload_str, (
        "M3: /events/upcoming leaks a soft-deleted person's name in the payload"
    )
    assert upcoming_ids == scheduler_ids, (
        "M3: /events/upcoming and the anniversary scheduler disagree on which "
        "events are due — /upcoming shows the soft-deleted person's event that "
        "the scheduler (correctly) already suppresses"
    )


# ── get_birth_dates repo-level exclusion ─────────────────────────────────


async def test_get_birth_dates_excludes_deleted(async_session: AsyncSession) -> None:
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    live = await _person(async_session, clan_id, creator, "Live")
    deleted = await _person(async_session, clan_id, creator, "Deleted")
    await async_session.execute(
        sa.text("UPDATE persons SET birth_date = :d WHERE id = :p"),
        {"d": date(1950, 1, 1), "p": live},
    )
    await async_session.execute(
        sa.text("UPDATE persons SET birth_date = :d WHERE id = :p"),
        {"d": date(1950, 1, 1), "p": deleted},
    )
    await async_session.commit()
    await _set_deleted(async_session, deleted, True)

    port = SqlAlchemyRelationshipQueryPort(async_session)
    dates = await port.get_birth_dates([live, deleted])

    assert live in dates  # control: live person's birth date is still returned
    assert deleted not in dates, "M3: get_birth_dates returns a soft-deleted person's birth_date"


# ── Identity claim resolution (SIXTH hole — claim_repository.get_person) ─


async def test_claim_creation_blocked_for_soft_deleted_person(
    async_session: AsyncSession,
) -> None:
    """M3 sixth write hole (found in final review, not the original sweep):
    ``claim_repository.get_person`` — used by ``submit_claim`` and
    ``prelink_identity`` to resolve the CLAIM TARGET — had no ``is_deleted``
    filter. A soft-deleted person could still be claimed (or admin-prelinked);
    once approved, a live user's ``user_profile.person_id`` would bind to an
    INVISIBLE person.

    Fix: a new ``get_live_person`` (is_deleted-filtered) is used only at the two
    claim-CREATION sites. ``get_person`` stays unfiltered for ``cancel_claim``'s
    non-gating audit-metadata lookup and ``unlink_identity``'s resolution of an
    ALREADY-established link — filtering those could strand a legitimate
    in-flight operation on a person soft-deleted after the fact, the same
    E3-cascade rationale this suite already applies to approve/reject.
    """
    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    uow = SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    handler = ClaimCommandHandler(SqlAlchemyClaimRepository(async_session), uow)

    async def _user(email: str) -> uuid.UUID:
        uid = uuid.uuid4()
        await async_session.execute(
            sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :em, 'U')"),
            {"id": uid, "em": email},
        )
        return uid

    # Restore-symmetry control — independent person+user pair (reusing the
    # blocked pair would hit user_already_has_pending_claim, a false signal
    # unrelated to this hole, per this file's established pattern).
    person_ctrl = await _person(async_session, clan_id, creator, "Ctrl")
    await _member(async_session, person_ctrl, clan_id)
    user_ctrl = await _user(f"ctrl-{uuid.uuid4().hex[:8]}@example.com")
    await async_session.commit()
    await _set_deleted(async_session, person_ctrl, True)
    await _set_deleted(async_session, person_ctrl, False)  # restored before use

    ctrl = await handler.submit_claim(user_id=user_ctrl, person_id=person_ctrl, requester_note=None)
    assert ctrl.person_id == person_ctrl

    # Blocked path: soft-deleted person.
    person = await _person(async_session, clan_id, creator, "Deleted")
    await _member(async_session, person, clan_id)
    user = await _user(f"blocked-{uuid.uuid4().hex[:8]}@example.com")
    await async_session.commit()
    await _set_deleted(async_session, person, True)

    with pytest.raises(EntityNotFoundError, match="person_not_found"):
        await handler.submit_claim(user_id=user, person_id=person, requester_note=None)


# ── Source-scan class gate ───────────────────────────────────────────────


def test_every_person_guard_filters_soft_deleted() -> None:
    """Source-scan gate: every person(s)_in_clan guard in the persistence layer
    must reference is_deleted. Catches the M3 class in FUTURE aggregates —
    runtime tests above prove today's five; this catches the sixth.

    Deliberately NOT a DB test (no fixtures used) — this is a pure static-source
    check kept here for cohesion with the rest of the M3 suite it future-proofs.

    SCOPE (read before assuming this gate covers a new guard): it only scans
    persistence-layer classes/methods literally named ``person_in_clan`` or
    ``persons_in_clan`` (see guard_method_names below). A person-existence guard
    under any OTHER name — e.g. claim_repository.get_live_person, which resolves
    the identity-claim target and is not clan-scoped so it was never named that
    way — is invisible to this scan and was in fact the SIXTH hole (found in
    final review, not by this gate). Any future differently-named resolver
    needs its own dedicated pinning test, the way
    test_claim_live_person_resolver_filters_soft_deleted below pins this one.
    """
    import importlib
    import inspect
    import pkgutil

    import app.infrastructure.persistence as persistence_pkg

    guard_method_names = {"person_in_clan", "persons_in_clan"}
    checked: list[str] = []

    for module_info in pkgutil.iter_modules(persistence_pkg.__path__):
        module_name = module_info.name
        if module_name.startswith("_"):
            continue
        module = importlib.import_module(f"{persistence_pkg.__name__}.{module_name}")

        for class_name, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module.__name__:
                continue  # skip re-exported/imported classes; only this module's own

            for method_name, method in inspect.getmembers(cls, inspect.isfunction):
                if method_name not in guard_method_names:
                    continue
                qualified_name = f"{module_name}.{class_name}.{method_name}"
                source = inspect.getsource(method)
                checked.append(qualified_name)
                assert "is_deleted" in source, (
                    f"M3 class gate: {qualified_name} does not filter is_deleted — "
                    "a person(s)_in_clan guard must exclude soft-deleted persons "
                    "from being treated as valid references"
                )

    assert checked, (
        "gate found zero person(s)_in_clan guards in app.infrastructure.persistence "
        "— the scan itself is broken (module/method discovery regressed)"
    )


def test_claim_live_person_resolver_filters_soft_deleted() -> None:
    """Dedicated pin for the SIXTH M3 hole: SqlAlchemyClaimRepository.get_live_person
    isn't named person(s)_in_clan, so test_every_person_guard_filters_soft_deleted's
    source-scan gate above does not (and by design cannot) see it. Pin it here
    explicitly so a future refactor can't silently drop its is_deleted filter
    without a test noticing."""
    import inspect

    from app.infrastructure.persistence.claim_repository import SqlAlchemyClaimRepository

    source = inspect.getsource(SqlAlchemyClaimRepository.get_live_person)
    assert "is_deleted" in source, (
        "SqlAlchemyClaimRepository.get_live_person must filter is_deleted — it "
        "resolves the identity-claim target and must not admit a soft-deleted person"
    )
