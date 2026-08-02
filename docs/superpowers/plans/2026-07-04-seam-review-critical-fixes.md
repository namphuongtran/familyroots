# Critical Seam-Review Fixes (C1–C3) Implementation Plan

> **STATUS: EXECUTED AND MERGED (2026-07-05). Historical record — do not execute.**
> All three PRs landed on `main`: C1 in #22 (`6b1f02c`), C3 in #23 (`0c750fc`),
> C2 in #24 (`1753d69`). This file was rescued on 2026-08-02 from the abandoned
> branch `docs/seam-review-2026-07-04`, where it was the only content that never
> reached `main`; it moved from `docs/plans/` (a directory `main` never had) into
> the current `docs/superpowers/plans/` location. Its source review,
> `docs/architecture/seam-review-2026-07-04.md`, was deliberately retired from
> `main` in `733decc` and is not linked below.

**Goal:** Fix the three Critical findings from the 2026-07-04 seam review (source document since retired) as three independent PRs: C1 FCM writes never committed, C2 scheduler leap-date crash + stranded advisory lock, C3 invitation accept/revoke race.

**Architecture:** Each fix restores an existing convention rather than inventing one: C1 routes the last UoW-less write path through `SqlAlchemyUnitOfWork`; C2 replaces raw `MAKE_DATE` with a clamped (last-day-of-month) SQL fragment shared by the scheduler and `get_upcoming`, and pins the advisory lock to one dedicated connection so mid-job commits can't strand it; C3 makes invitation status transitions atomic conditional UPDATEs (`WHERE status='pending'`, rowcount-checked) behind the existing domain port.

**Tech Stack:** FastAPI, SQLAlchemy 2 async (psycopg), PostgreSQL, APScheduler, pytest(-asyncio) against dockerized Postgres.

## Global Constraints

- All write operations flow through Unit of Work (repo-root CLAUDE.md).
- Domain layer stays framework-free; `app/domain/**` may not import SQLAlchemy (enforced by import-linter after PR #20).
- Error envelope codes are contract-stable: reuse `invitation.not_pending` (already in `docs/contracts/rest-invitations-api.md`); no new codes.
- Product decisions (owner-confirmed 2026-07-04): Feb-29 anniversaries observe **Feb 28** in non-leap years (clamp to last day of month); revoking an already-accepted invitation returns **409 `invitation.not_pending`** (membership removal stays in member management).
- Each PR ships alone: branch off main, full gate green (`backend/scripts/check.sh` once PR #20 is merged; otherwise `uv run ruff format --check . && uv run ruff check . && uv run mypy app/ tests/ && uv run pytest`), then push + PR per the team cadence.
- Integration tests need `docker compose up -d pgdb` from the repo root.
- All commands below run from `backend/` unless noted.

**Prerequisite:** PRs #20 and #21 are merged (or at least #20, for `scripts/check.sh` and the smoke suite). Do not stack branches; base every branch on current `origin/main`.

---

### Task 1 (PR-F, branch `fix/fcm-token-commit`): FCM token writes go through the Unit of Work

**Files:**
- Modify: `backend/app/application/auth/handlers.py:312-322` (`FCMTokenHandler`)
- Modify: `backend/app/infrastructure/dependencies.py` (`get_fcm_token_handler`)
- Test: `backend/tests/integration/test_fcm_token_persistence.py` (new)

**Interfaces:**
- Consumes: `SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))` (existing), `SqlAlchemyFCMTokenRepository` (existing, unchanged), `UnitOfWork` protocol from `app.domain.shared.unit_of_work`.
- Produces: `FCMTokenHandler.__init__(self, repo: FCMTokenRepository, uow: UnitOfWork)` — the DI provider and any future test must pass both.

- [ ] **Step 1: Write the failing integration test** — persistence must survive session close, which is exactly what the bug violates. Create `backend/tests/integration/test_fcm_token_persistence.py`:

```python
"""C1 regression (seam-review-2026-07-04): FCM token writes must COMMIT.

The bug: FCMTokenHandler had no UnitOfWork and nothing else in the chain
committed, so the INSERT rolled back at session close while the API returned
success. The test writes through the real handler wiring in one session, then
verifies from a SECOND session — a flush-only write cannot pass it.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.application.auth.handlers import FCMTokenHandler
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.auth_repository import SqlAlchemyFCMTokenRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


def _handler(db: AsyncSession) -> FCMTokenHandler:
    # Mirror get_fcm_token_handler in app/infrastructure/dependencies.py.
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return FCMTokenHandler(SqlAlchemyFCMTokenRepository(db), uow)


async def _seed_profile(maker: async_sessionmaker[AsyncSession], user_id: uuid.UUID) -> None:
    async with maker() as s:
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) "
                "VALUES (:id, :em, 'FCM Tester') ON CONFLICT (id) DO NOTHING"
            ),
            {"id": user_id, "em": f"fcm-{user_id.hex[:8]}@example.com"},
        )
        await s.commit()


@pytest.mark.asyncio
async def test_register_token_persists_across_sessions(engine: AsyncEngine) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    user_id = uuid.uuid4()
    token = f"tok-{uuid.uuid4().hex}"
    await _seed_profile(maker, user_id)

    async with maker() as db:  # request session: handler must commit itself
        await _handler(db).register_token(
            user_id=str(user_id), token=token, device_platform="android"
        )

    async with maker() as db:  # fresh session: only committed rows are visible
        n = await db.scalar(
            sa.text("SELECT COUNT(*) FROM user_fcm_tokens WHERE token = :t"), {"t": token}
        )
    assert n == 1, "register_token was rolled back at session close (C1 regression)"


@pytest.mark.asyncio
async def test_remove_token_persists_across_sessions(engine: AsyncEngine) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    user_id = uuid.uuid4()
    token = f"tok-{uuid.uuid4().hex}"
    await _seed_profile(maker, user_id)

    async with maker() as db:
        await _handler(db).register_token(
            user_id=str(user_id), token=token, device_platform="ios"
        )
    async with maker() as db:
        await _handler(db).remove_token(user_id=str(user_id), token=token)

    async with maker() as db:
        n = await db.scalar(
            sa.text("SELECT COUNT(*) FROM user_fcm_tokens WHERE token = :t"), {"t": token}
        )
    assert n == 0, "remove_token was rolled back at session close (C1 regression)"
```

Note: check `user_fcm_tokens`' FK before finalizing `_seed_profile` — migration 004 references `user_profiles(id)`. If it turns out there is no FK, `_seed_profile` can be dropped.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/integration/test_fcm_token_persistence.py -v`
Expected: both tests FAIL — first with `TypeError: FCMTokenHandler.__init__() takes 2 positional arguments but 3 were given` (constructor doesn't accept a UoW yet). After temporarily reverting `_handler` to one argument you would see `assert 0 == 1` (the true C1 symptom); no need to actually do that — the TypeError already proves the seam is missing.

- [ ] **Step 3: Give FCMTokenHandler a UnitOfWork** — in `backend/app/application/auth/handlers.py` replace the class:

```python
class FCMTokenHandler:
    """Handles FCM push token registration.

    Writes commit through the UoW like every other command handler — device
    tokens emit no domain events, but the commit discipline is what guarantees
    the write survives the request (C1, seam-review-2026-07-04)."""

    def __init__(self, repo: FCMTokenRepository, uow: UnitOfWork) -> None:
        self._repo = repo
        self._uow = uow

    async def register_token(self, *, user_id: str, token: str, device_platform: str) -> None:
        await self._repo.register_token(user_id, token, device_platform)
        await self._uow.commit()

    async def remove_token(self, *, user_id: str, token: str) -> None:
        await self._repo.remove_token(user_id, token)
        await self._uow.commit()
```

(`UnitOfWork` is already imported in this module at line 31.)

- [ ] **Step 4: Wire the UoW in the composition root** — in `backend/app/infrastructure/dependencies.py` replace `get_fcm_token_handler`:

```python
def get_fcm_token_handler(db: AsyncSession = Depends(get_db)) -> FCMTokenHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return FCMTokenHandler(SqlAlchemyFCMTokenRepository(db), uow)
```

- [ ] **Step 5: Run the new tests + the DI/unit suites**

Run: `uv run pytest tests/integration/test_fcm_token_persistence.py tests/unit/test_di_providers.py tests/test_auth.py -v`
Expected: all PASS (the DI discovery test exercises the new provider shape automatically).

- [ ] **Step 6: Full gate**

Run: `./scripts/check.sh`
Expected: `Gate passed.` (306+ tests, 5/5 import contracts).

- [ ] **Step 7: Commit and open PR-F**

```bash
git add app/application/auth/handlers.py app/infrastructure/dependencies.py tests/integration/test_fcm_token_persistence.py
git commit -m "fix(backend): commit FCM token writes through the UoW (C1)

Seam-review C1: FCMTokenHandler was the only write path without a UnitOfWork;
get_db never commits, so register/remove flushed and then rolled back at
session close while the route returned success — push notifications were
silently dead. Handler now takes the UoW and commits; regression test writes
through the real wiring and asserts visibility from a second session."
```

Push `fix/fcm-token-commit`, open PR titled `fix(backend): commit FCM token writes through the UoW (C1)`.

---

### Task 2 (PR-G1, branch `fix/invitation-race`): atomic invitation status transitions

**Files:**
- Modify: `backend/app/domain/invitation/repository.py` (add `transition_status` to the protocol)
- Modify: `backend/app/infrastructure/persistence/invitation_repository.py` (implement it)
- Modify: `backend/app/application/invitation/handlers.py:75-145` (`accept`, `revoke`)
- Test: `backend/tests/unit/application/test_invitation_handlers.py` (extend)
- Test: `backend/tests/integration/test_invitation_race.py` (new)

**Interfaces:**
- Consumes: existing `InvitationRepository` protocol methods; `ConflictError("invitation.not_pending")` from `app.domain.shared.exceptions` (already imported in the handler).
- Produces: `async def transition_status(self, invitation_id: uuid.UUID, *, expected: str, to: str, accepted_by: uuid.UUID | None = None, accepted_at: datetime | None = None) -> bool` on both the protocol and the SQLAlchemy repo. Returns True iff exactly one row moved `expected → to`.

- [ ] **Step 1: Extend the domain port** — in `backend/app/domain/invitation/repository.py` add to the protocol (plus `from datetime import datetime` at the top; the file already imports `uuid`):

```python
    async def transition_status(
        self,
        invitation_id: uuid.UUID,
        *,
        expected: str,
        to: str,
        accepted_by: uuid.UUID | None = None,
        accepted_at: datetime | None = None,
    ) -> bool:
        """Atomically move status ``expected`` → ``to``.

        Returns False (and writes nothing) if the row is no longer in
        ``expected`` — the DB-side guard that closes the accept×revoke race
        (C3, seam-review-2026-07-04). The in-memory status checks in the
        handler remain only as fast, friendly-error paths."""
        ...
```

- [ ] **Step 2: Write failing unit tests for the handler behavior** — in `backend/tests/unit/application/test_invitation_handlers.py`, first read the file's existing fake-repo pattern and mirror it. Add a `transition_status` to the existing fake repo that records calls and returns a configurable result, then add:

```python
@pytest.mark.asyncio
async def test_accept_conflicts_when_transition_loses_race(...) -> None:
    # fake repo: get_by_token returns a pending invitation,
    # transition_status returns False (a concurrent revoke won the row)
    with pytest.raises(ConflictError, match="invitation.not_pending"):
        await handler.accept(make_accept_cmd(...))
    # and no role was granted:
    assert fake_repo.added_roles == []


@pytest.mark.asyncio
async def test_revoke_conflicts_when_transition_loses_race(...) -> None:
    # fake repo: get_by_id returns a pending invitation,
    # transition_status returns False (a concurrent accept won the row)
    with pytest.raises(ConflictError, match="invitation.not_pending"):
        await handler.revoke(make_revoke_cmd(...))


@pytest.mark.asyncio
async def test_accept_claims_before_granting_role(...) -> None:
    # fake repo records call order: transition_status must precede add_user_role,
    # so a lost race can never leave a granted role behind.
    await handler.accept(make_accept_cmd(...))
    assert fake_repo.call_order.index("transition_status") < fake_repo.call_order.index("add_user_role")
```

(Adapt names to the file's existing fixtures — the file already builds handlers with a fake repo and fake UoW; extend those fakes rather than inventing parallel ones. The three assertions above are the required behavior; keep them verbatim in spirit.)

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/unit/application/test_invitation_handlers.py -v`
Expected: new tests FAIL (`AttributeError: ... has no attribute 'transition_status'` or the ConflictError is not raised); pre-existing tests still pass.

- [ ] **Step 4: Implement the repo method** — in `backend/app/infrastructure/persistence/invitation_repository.py` (add `from datetime import datetime` and extend the sqlalchemy import to `from sqlalchemy import desc, select, update`):

```python
    async def transition_status(
        self,
        invitation_id: uuid.UUID,
        *,
        expected: str,
        to: str,
        accepted_by: uuid.UUID | None = None,
        accepted_at: datetime | None = None,
    ) -> bool:
        values: dict[str, object] = {"status": to}
        if accepted_by is not None:
            values["accepted_by"] = accepted_by
        if accepted_at is not None:
            values["accepted_at"] = accepted_at
        result = await self._session.execute(
            update(ClanInvitation)
            .where(ClanInvitation.id == invitation_id, ClanInvitation.status == expected)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return bool(result.rowcount)
```

- [ ] **Step 5: Rewire the handler** — in `backend/app/application/invitation/handlers.py`:

In `accept`, replace lines 86-111 (the block from `ensure_profile` through `inv.accepted_at = …`) so the row is claimed FIRST — a lost claim must never leave role work behind, and a successful claim row-locks the invitation so a concurrent revoke waits and then misses:

```python
        # Claim the invitation atomically BEFORE any membership work: if a
        # concurrent revoke (or another accept) already moved it out of
        # "pending", we stop here with the contract's 409 and the transaction
        # never grants anything.
        claimed = await self._repo.transition_status(
            inv.id,
            expected="pending",
            to="accepted",
            accepted_by=cmd.user_id,
            accepted_at=datetime.now(UTC),
        )
        if not claimed:
            raise ConflictError("invitation.not_pending")

        await self._repo.ensure_profile(cmd.user_id, cmd.user_email, cmd.user_full_name)

        existing = await self._repo.get_user_role(cmd.user_id, inv.clan_id)
        if existing and existing.is_approved:
            raise ConflictError("invitation.already_member")
        if existing and not existing.is_approved:
            # Promote the pending self-request to approved with the invited role.
            existing.role = inv.role
            existing.is_approved = True
            existing.approved_by = inv.invited_by
            existing.approved_at = datetime.now(UTC)
        else:
            self._repo.add_user_role(
                UserClanRole(
                    clan_id=inv.clan_id,
                    user_id=cmd.user_id,
                    role=inv.role,
                    is_approved=True,
                    approved_by=inv.invited_by,
                    approved_at=datetime.now(UTC),
                )
            )
```

(The `already_member` raise after a successful claim rolls back the whole transaction, claim included — correct: the invitation stays pending. Keep the pre-existing status/expiry/email checks at the top of `accept` untouched — they produce the friendly errors for the common cases.)

In `revoke`, replace lines 131-133 (`if inv.status != "pending": raise …` / `inv.status = "revoked"`):

```python
        if inv.status != "pending":
            raise ConflictError("invitation.not_pending")
        # Atomic guard: an accept that committed after our read wins the row;
        # per owner decision (2026-07-04) revoke-after-accept is a 409 and
        # membership removal stays in member management.
        claimed = await self._repo.transition_status(inv.id, expected="pending", to="revoked")
        if not claimed:
            raise ConflictError("invitation.not_pending")
```

- [ ] **Step 6: Run the unit suite**

Run: `uv run pytest tests/unit/application/test_invitation_handlers.py -v`
Expected: all PASS.

- [ ] **Step 7: Write the integration race test** — create `backend/tests/integration/test_invitation_race.py`:

```python
"""C3 regression (seam-review-2026-07-04): invitation transitions are atomic.

Two levels: (1) repo-level — a conditional UPDATE from a second session blocks
on the first session's row lock and returns False after it commits; (2)
handler-level — revoke after a committed accept is a 409 and leaves the
granted membership in place (owner-decided policy), never a silently-revoked
invitation with a live member.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.application.invitation.commands import AcceptInvitation, RevokeInvitation
from app.application.invitation.handlers import InvitationCommandHandler
from app.domain.shared.exceptions import ConflictError
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.invitation_repository import SqlAlchemyInvitationRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


def _maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _seed(maker: async_sessionmaker[AsyncSession]) -> dict:
    """Clan + admin profile + a pending invitation; returns ids/token/email."""
    clan_id, admin_id, inv_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    token = f"race-{uuid.uuid4().hex}"
    email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) "
                "VALUES (:id, :em, 'Admin')"
            ),
            {"id": admin_id, "em": f"admin-{admin_id.hex[:8]}@example.com"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO clan_invitations "
                "(id, clan_id, email, role, invited_by, token, expires_at, status) "
                "VALUES (:id, :clan, :em, 'viewer', :by, :tok, :exp, 'pending')"
            ),
            {
                "id": inv_id, "clan": clan_id, "em": email, "by": admin_id,
                "tok": token, "exp": datetime.now(UTC) + timedelta(days=7),
            },
        )
        await s.commit()
    return {"clan_id": clan_id, "admin_id": admin_id, "inv_id": inv_id,
            "token": token, "email": email}


def _handler(db: AsyncSession) -> InvitationCommandHandler:
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return InvitationCommandHandler(SqlAlchemyInvitationRepository(db), uow)


@pytest.mark.asyncio
async def test_conditional_update_blocks_then_misses(engine: AsyncEngine) -> None:
    """Repo level: S2's transition blocks on S1's uncommitted claim, then
    returns False once S1 commits — the row can only move out of pending once."""
    maker = _maker(engine)
    seeded = await _seed(maker)

    async with maker() as s1, maker() as s2:
        repo1, repo2 = SqlAlchemyInvitationRepository(s1), SqlAlchemyInvitationRepository(s2)

        won = await repo1.transition_status(seeded["inv_id"], expected="pending", to="accepted")
        assert won is True  # uncommitted — holds the row lock

        task = asyncio.create_task(
            repo2.transition_status(seeded["inv_id"], expected="pending", to="revoked")
        )
        done, _ = await asyncio.wait({task}, timeout=0.3)
        assert not done, "second transition should block on the row lock"

        await s1.commit()
        lost = await asyncio.wait_for(task, timeout=5)
        assert lost is False, "after the winner commits, the loser must miss"
        await s2.rollback()


@pytest.mark.asyncio
async def test_revoke_after_accept_is_409_and_keeps_membership(engine: AsyncEngine) -> None:
    """Handler level: the exact C3 scenario — before the fix, this revoke
    returned success and overwrote the accepted invitation."""
    maker = _maker(engine)
    seeded = await _seed(maker)
    invitee_id = uuid.uuid4()

    async with maker() as db:
        await _handler(db).accept(
            AcceptInvitation(
                token=seeded["token"], user_id=invitee_id,
                user_email=seeded["email"], user_full_name="Invitee",
            )
        )

    async with maker() as db:
        with pytest.raises(ConflictError, match="invitation.not_pending"):
            await _handler(db).revoke(
                RevokeInvitation(
                    invitation_id=seeded["inv_id"], clan_id=seeded["clan_id"],
                    actor=ActorInfo(user_id=seeded["admin_id"], role="admin"),
                )
            )

    async with maker() as s:
        status = await s.scalar(
            sa.text("SELECT status FROM clan_invitations WHERE id = :id"),
            {"id": seeded["inv_id"]},
        )
        roles = await s.scalar(
            sa.text(
                "SELECT COUNT(*) FROM user_clan_roles "
                "WHERE user_id = :u AND clan_id = :c AND is_approved = true"
            ),
            {"u": invitee_id, "c": seeded["clan_id"]},
        )
    assert status == "accepted", "revoke must not overwrite an accepted invitation"
    assert roles == 1, "the granted membership stays; removal is member management's job"
```

Before finalizing, check the real field names of `AcceptInvitation` / `RevokeInvitation` in `backend/app/application/invitation/commands.py` and adjust the constructor calls; check `clan_invitations` NOT NULL columns against migration 001 (add any missing seed columns).

- [ ] **Step 8: Run the integration tests**

Run: `uv run pytest tests/integration/test_invitation_race.py tests/integration/test_invitation_accept.py tests/integration/test_invitation_repository.py -v`
Expected: all PASS (the two pre-existing invitation suites prove no regression in the happy paths).

- [ ] **Step 9: Full gate**

Run: `./scripts/check.sh`
Expected: `Gate passed.`

- [ ] **Step 10: Commit and open PR-G1**

```bash
git add app/domain/invitation/repository.py app/infrastructure/persistence/invitation_repository.py app/application/invitation/handlers.py tests/unit/application/test_invitation_handlers.py tests/integration/test_invitation_race.py
git commit -m "fix(backend): atomic invitation status transitions (C3)

Seam-review C3: accept and revoke checked status on an in-memory snapshot and
wrote unconditionally, so accept racing revoke left the user an approved
member while the invitation read revoked — both requests 200. Transitions now
go through a conditional UPDATE (WHERE status='pending') behind the domain
port; the loser gets the contract's 409 invitation.not_pending. Accept claims
the row before any membership work. Owner decision: revoke-after-accept is
409; membership removal stays in member management."
```

Push `fix/invitation-race`, open PR titled `fix(backend): atomic invitation status transitions (C3)`.

---

### Task 3 (PR-H1, branch `fix/scheduler-leap-lock`): leap-safe anniversary dates + un-strandable advisory lock

**Files:**
- Create: `backend/app/infrastructure/persistence/sql_dates.py`
- Modify: `backend/app/services/scheduler.py:39-133`
- Modify: `backend/app/infrastructure/persistence/event_repository.py:66-110` (`get_upcoming` CTE)
- Test: `backend/tests/integration/test_scheduler_lock.py` (extend — also update its `AsyncSessionLocal` monkeypatch to the new `engine` seam)
- Test: `backend/tests/integration/test_anniversary_dates.py` (new)

**Interfaces:**
- Consumes: `app.core.database.engine` (module-level async engine — the scheduler imports it lazily inside the job so tests can monkeypatch `app.core.database.engine`).
- Produces: `def next_anniversary_sql(year_sql: str, date_col: str = "e.event_date") -> str` in `sql_dates.py` — returns a SQL expression (a `::date` value) for "the month/day of `date_col` in year `year_sql`, clamped to that month's last day".

- [ ] **Step 1: Write the failing date test** — create `backend/tests/integration/test_anniversary_dates.py`:

```python
"""C2 regression (seam-review-2026-07-04): Feb-29 recurring events must not
crash occurrence computation; non-leap years observe Feb 28 (owner decision).

Before the fix, MAKE_DATE(year, 2, 29) raised 'date field value out of range',
aborting the scheduler's whole SELECT (killing the nightly job for every clan)
and the /events/upcoming query.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence.event_repository import SqlAlchemyEventRepository
from app.infrastructure.persistence.sql_dates import next_anniversary_sql


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_sql_fragment_clamps_feb_29(engine: AsyncEngine) -> None:
    """The shared fragment: Feb-29 anniversary in 2026 (non-leap) → Feb 28;
    in 2028 (leap) → Feb 29; ordinary dates pass through unchanged."""
    frag = next_anniversary_sql(":year", date_col=":d ::date")
    async with engine.connect() as conn:
        for year, event_date, expected in [
            (2026, date(2024, 2, 29), date(2026, 2, 28)),
            (2028, date(2024, 2, 29), date(2028, 2, 29)),
            (2026, date(2020, 3, 10), date(2026, 3, 10)),
            (2026, date(2019, 12, 31), date(2026, 12, 31)),
        ]:
            got = await conn.scalar(
                sa.text(f"SELECT {frag}"), {"year": year, "d": event_date}
            )
            assert got == expected, f"{event_date} in {year}: {got} != {expected}"


async def _seed_clan_with_feb29_event(
    maker: async_sessionmaker[AsyncSession],
) -> uuid.UUID:
    clan_id = uuid.uuid4()
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :sg)"),
            {"id": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO events (id, clan_id, event_type, title, event_date, "
                "is_recurring, notify_days_before, created_by) "
                "VALUES (:id, :clan, 'death_anniversary', 'Giỗ 29/2', :d, true, 7, :cb)"
            ),
            {"id": uuid.uuid4(), "clan": clan_id, "d": date(2024, 2, 29), "cb": uuid.uuid4()},
        )
        await s.commit()
    return clan_id


@pytest.mark.asyncio
async def test_get_upcoming_survives_feb29_and_clamps(engine: AsyncEngine) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    clan_id = await _seed_clan_with_feb29_event(maker)

    async with maker() as s:
        repo = SqlAlchemyEventRepository(s)
        # A window in a NON-leap year that covers Feb 28: the event must appear,
        # clamped — before the fix this raised DataError.
        rows = await repo.get_upcoming(
            clan_id, today=date(2026, 2, 20), end_date=date(2026, 3, 20)
        )
    occurrences = {r["next_occurrence"] for r in rows}
    assert date(2026, 2, 28) in occurrences
```

Before finalizing, read `SqlAlchemyEventRepository.get_upcoming`'s row shape (dict keys) and the `events` table NOT NULL columns; adjust seeds/keys if needed.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_anniversary_dates.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.infrastructure.persistence.sql_dates'`, and (once the module exists but `get_upcoming` is unfixed) `DataError: date field value out of range: 2026-02-29` from the second test.

- [ ] **Step 3: Create the shared SQL fragment** — `backend/app/infrastructure/persistence/sql_dates.py`:

```python
"""Leap-safe SQL date fragments shared by the anniversary job and event reads.

``MAKE_DATE(year, month, day)`` raises for Feb 29 in non-leap years — and one
such error aborts the WHOLE statement it appears in (C2,
seam-review-2026-07-04). These fragments never construct an invalid date:
they build day 1 of the month and add day-offsets, clamping to the month's
last day. Owner decision 2026-07-04: Feb-29 anniversaries observe Feb 28 in
non-leap years.
"""


def next_anniversary_sql(year_sql: str, date_col: str = "e.event_date") -> str:
    """SQL ``::date`` expression: the month/day of ``date_col`` in year
    ``year_sql``, clamped to that month's last day (Feb 29 → Feb 28)."""
    first_of_month = f"MAKE_DATE(({year_sql})::int, EXTRACT(MONTH FROM {date_col})::int, 1)"
    return (
        f"LEAST(({first_of_month} + (EXTRACT(DAY FROM {date_col})::int - 1) * INTERVAL '1 day')::date, "
        f"({first_of_month} + INTERVAL '1 month' - INTERVAL '1 day')::date)"
    )
```

- [ ] **Step 4: Use it in `get_upcoming`** — in `backend/app/infrastructure/persistence/event_repository.py`, import it (`from app.infrastructure.persistence.sql_dates import next_anniversary_sql`) and replace the recurring-branch CASE inside the CTE (the `WHEN e.is_recurring THEN CASE … END` block) with:

```python
        this_year = next_anniversary_sql("EXTRACT(YEAR FROM :today)", "e.event_date")
        next_year = next_anniversary_sql("EXTRACT(YEAR FROM :today) + 1", "e.event_date")
```

and in the SQL string:

```sql
                        CASE
                            WHEN e.is_recurring THEN
                                CASE
                                    WHEN {this_year} >= :today THEN {this_year}
                                    ELSE {next_year}
                                END
                            ELSE e.event_date
                        END AS next_occurrence
```

(the query becomes an f-string over trusted, code-built fragments — no user input is interpolated; bind params `:today`, `:clan_id`, `:end_date` stay bind params).

- [ ] **Step 5: Run the date tests**

Run: `uv run pytest tests/integration/test_anniversary_dates.py -v`
Expected: PASS.

- [ ] **Step 6: Write the failing lock-hygiene tests** — extend `backend/tests/integration/test_scheduler_lock.py` with two tests (and a helper). These fail against the current implementation because (a) after a mid-loop commit the unlock lands on a different pooled connection (lock stranded), and (b) a mid-job exception leaves the session aborted so the `finally` unlock raises, masking the original error:

```python
async def _lock_is_free(engine: AsyncEngine) -> bool:
    """Probe from a brand-new connection; release immediately if acquired."""
    async with engine.connect() as probe:
        got = await probe.execute(
            sa.text("SELECT pg_try_advisory_lock(:k)"), {"k": scheduler._JOB_LOCK_KEY}
        )
        acquired = bool(got.scalar())
        if acquired:
            await probe.execute(
                sa.text("SELECT pg_advisory_unlock(:k)"), {"k": scheduler._JOB_LOCK_KEY}
            )
        await probe.rollback()
    return acquired


@pytest.mark.asyncio
async def test_lock_released_even_after_midjob_commit(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C2 regression: processing a due event commits mid-job; the unlock must
    still land on the lock-holding connection. Before the fix the lock was
    stranded on an idle pooled connection and later runs skipped forever."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    spy = AsyncMock()
    monkeypatch.setattr("app.services.notification.send_to_clan", spy)

    await _seed_due_event(maker)
    await scheduler.send_anniversary_notifications()  # sends + commits mid-job

    assert spy.await_count == 1
    assert await _lock_is_free(async_engine), "advisory lock stranded after mid-job commit"


@pytest.mark.asyncio
async def test_lock_released_and_error_propagates_after_failure(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C2 regression: a mid-job failure must roll back before unlocking, so the
    ORIGINAL error propagates (not InFailedSqlTransaction) and the lock frees."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr("app.core.database.engine", async_engine)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    boom = RuntimeError("fcm exploded")
    monkeypatch.setattr(
        "app.services.notification.send_to_clan", AsyncMock(side_effect=boom)
    )

    await _seed_due_event(maker)
    with pytest.raises(RuntimeError, match="fcm exploded"):
        await scheduler.send_anniversary_notifications()

    assert await _lock_is_free(async_engine), "advisory lock stranded after job failure"
```

Also update the two existing tests in this file to add `monkeypatch.setattr("app.core.database.engine", async_engine)` alongside their existing `AsyncSessionLocal` patch (the job will draw its lock connection from the engine).

- [ ] **Step 7: Run to verify failure**

Run: `uv run pytest tests/integration/test_scheduler_lock.py -v`
Expected: the two new tests FAIL (stranded lock → `_lock_is_free` False, and/or `InternalError` instead of `RuntimeError`); the two old tests still pass.

- [ ] **Step 8: Rewrite the job's connection/lock topology** — in `backend/app/services/scheduler.py`, replace `send_anniversary_notifications` body structure (keeping the query/loop logic, with the clamped dates):

```python
async def send_anniversary_notifications() -> None:
    """Daily job: find events with upcoming anniversaries and send FCM notifications.

    Lock topology (C2, seam-review-2026-07-04): the advisory lock lives on ONE
    dedicated connection held for the whole job; the working session is bound
    to that same connection, so mid-job commits can't release it back to the
    pool and strand the lock. The finally block rolls back before unlocking so
    a failed job can't mask its own error with InFailedSqlTransaction.
    """
    from app.core.database import engine
    from app.infrastructure.persistence.sql_dates import next_anniversary_sql
    from app.services.notification import send_to_clan

    today = date.today()
    this_year = next_anniversary_sql("EXTRACT(YEAR FROM CURRENT_DATE)")
    next_year = next_anniversary_sql("EXTRACT(YEAR FROM CURRENT_DATE) + 1")

    async with engine.connect() as conn:
        acquired = await conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": _JOB_LOCK_KEY}
        )
        if not acquired.scalar():
            logger.info("Anniversary job lock held by another instance — skipping this run")
            await conn.rollback()
            return
        # End the autobegun transaction the lock SELECT opened (the
        # session-level advisory lock survives commit). Otherwise the bound
        # session below would JOIN that transaction via savepoints and its
        # commits would not be durable until the connection commits.
        await conn.commit()

        db = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            result = await db.execute(
                text(f"""
                    SELECT
                        e.id AS event_id,
                        e.clan_id,
                        e.event_type,
                        e.title,
                        e.person_id,
                        p.full_name AS person_name,
                        e.notify_days_before,
                        CASE
                            WHEN {this_year} >= CURRENT_DATE THEN {this_year}
                            ELSE {next_year}
                        END AS next_occurrence
                    FROM public.events e
                    LEFT JOIN public.persons p ON p.id = e.person_id
                    WHERE e.is_recurring = true
                """)
            )
            events = result.mappings().all()

            # … existing per-event loop unchanged (days_until check, dedup
            # SELECT, send_to_clan(db=db), notification_log INSERT, db.commit()) …
        finally:
            # Roll back any open/aborted transaction BEFORE unlocking: the
            # session-level advisory lock survives rollback, and unlocking on
            # an aborted tx would raise and mask the job's real error.
            await db.rollback()
            await db.close()
            await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _JOB_LOCK_KEY})
            await conn.commit()
```

Required import change at the top of the file: `from sqlalchemy.ext.asyncio import AsyncSession`. The `AsyncSessionLocal` lazy import is no longer needed inside the function.

- [ ] **Step 9: Run the full scheduler + dates suites**

Run: `uv run pytest tests/integration/test_scheduler_lock.py tests/integration/test_anniversary_dates.py tests/test_notifications.py -v`
Expected: all PASS (including the two pre-existing lock tests, proving the skip/process behavior is unchanged).

- [ ] **Step 10: Full gate**

Run: `./scripts/check.sh`
Expected: `Gate passed.`

- [ ] **Step 11: Commit and open PR-H1**

```bash
git add app/infrastructure/persistence/sql_dates.py app/services/scheduler.py app/infrastructure/persistence/event_repository.py tests/integration/test_scheduler_lock.py tests/integration/test_anniversary_dates.py
git commit -m "fix(backend): leap-safe anniversary dates + un-strandable scheduler lock (C2)

Seam-review C2 (empirically verified): one recurring Feb-29 event made
MAKE_DATE raise, aborting the scheduler's whole SELECT — zero notifications
for every clan — and the failed finally-unlock stranded the session-level
advisory lock so later nights were skipped as 'lock held'. Same crash in
/events/upcoming. Dates now come from a shared clamped fragment (Feb 29 →
Feb 28 in non-leap years, owner decision); the lock lives on one dedicated
connection with the working session bound to it, and the job rolls back
before unlocking so failures propagate instead of masking themselves."
```

Push `fix/scheduler-leap-lock`, open PR titled `fix(backend): leap-safe anniversary dates + un-strandable scheduler lock (C2)`.

---

## Out of scope (deliberately — these are the Important-tier fixes)

Per-event error isolation, i18n key mismatch, lunar-calendar handling, `auth.users` join, sync-FCM off-loop (all PR-H proper); IntegrityError→409 handler and claim-transition guards (PR-G proper); `ensure_user_profile` phantom-write fix (PR-F proper). Fix classes were defined in seam-review-2026-07-04 §5 (document retired from `main` in `733decc`).

## Verification discipline (applies to every task)

Real-DB integration tests with two-session visibility checks (a flush is not a commit); negative controls included (lock-held skip, race-loser 409); full gate (`scripts/check.sh`) before every PR; each PR independently revertable.
