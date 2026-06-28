# SP-2A: Write-Path Correctness & User Provisioning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the three broken/incorrect write-path behaviours in the FamilyRoots backend: audit rows silently dropped on handler failure, the `IdentityClaim` approve/reject `AttributeError` crash, and the registration FK-violation caused by creating a `UserClanRole` before any `user_profiles` row exists.

**Architecture:** All writes already flow through `SqlAlchemyUnitOfWork.commit()` (flush → dispatch domain events → commit). We (1) make the event dispatcher propagate handler failures so audit writes are transactional, (2) make `ClaimCommandHandler.approve_claim`/`reject_claim` use the same `self._repo`/`self._uow` pattern the rest of that file already uses (the current `self._db` references are a latent crash), and (3) add an idempotent `ensure_profile` to the auth repository, invoked inside `_assign_clan_membership` before any membership row is inserted, with clan+profile+role committed atomically.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.0 async, asyncpg, Alembic, pytest + pytest-asyncio, `uv`. Local Postgres via `docker compose up -d pgdb` (postgres/postgres on localhost:5432).

## Global Constraints

- Python `>=3.14`; line length 100; ruff selectors per `pyproject.toml`.
- Domain layer stays framework-agnostic. Application layer imports domain + ports only, never infrastructure or FastAPI.
- All write paths flow through the Unit of Work; handlers must NOT call `session.commit()` directly. Use `self._uow.commit()` / `self._repo.add_*`.
- Audit rows are part of the same transaction as the business write — a failed audit write MUST abort the commit (ADR: auditability).
- `user_profiles.id` equals the Supabase `auth.users.id` (the JWT `sub`); it has NO DB foreign key to `auth.users`, so the backend owns provisioning. `ensure_profile` must be idempotent (get-or-create).
- The DB session uses `expire_on_commit=False`, so ORM attributes set before `commit()` remain readable after it (no post-commit `refresh` needed to serialize a response).
- Run tests: `cd backend && uv run pytest <path> -v`. Lint: `cd backend && uvx ruff check <path>`.
- Local DB admin DSN for integration tests: `postgresql+psycopg2://postgres:postgres@localhost:5432/postgres` (the `tests/integration` fixture already defaults to this).

---

## Files

- Modify: `backend/app/infrastructure/event_dispatcher.py` — re-raise handler exceptions.
- Test: `backend/tests/unit/infrastructure/test_event_dispatcher.py` — add propagation test.
- Modify: `backend/app/application/person/claim_handlers.py` — replace `self._db.*` in `approve_claim` (l.174-177) and `reject_claim` (l.214-217) with `self._repo.add_audit` + `self._uow.commit`.
- Create: `backend/tests/unit/application/__init__.py`
- Create: `backend/tests/unit/application/test_claim_command_handler.py` — approve/reject use UoW, no `self._db`.
- Modify: `backend/app/domain/auth/repository.py` — add `ensure_profile` to the `AuthRepository` protocol.
- Modify: `backend/app/infrastructure/persistence/auth_repository.py` — implement `ensure_profile`.
- Modify: `backend/app/application/auth/handlers.py` — call `ensure_profile` in `_assign_clan_membership`; make the create branch atomic.
- Test: `backend/tests/integration/test_auth_provisioning.py` — registration provisions a profile and the membership insert succeeds against a real DB.

---

## Task 1: Event dispatcher propagates handler failures (audit integrity)

**Files:**
- Modify: `backend/app/infrastructure/event_dispatcher.py:41-53`
- Test: `backend/tests/unit/infrastructure/test_event_dispatcher.py`

**Interfaces:**
- Produces: `InMemoryEventDispatcher.dispatch` raises if any handler raises (after logging). `SqlAlchemyUnitOfWork.commit` therefore aborts before `session.commit()` when an audit write fails.

- [ ] **Step 1: Add the failing test**

Read `backend/tests/unit/infrastructure/test_event_dispatcher.py` first, then append this test (it uses the existing `AuditableEvent`/dispatcher imports — match the file's existing import style; add imports only if missing):

```python
import pytest

from app.infrastructure.event_dispatcher import InMemoryEventDispatcher
from app.domain.shared.events import DomainEvent


@pytest.mark.asyncio
async def test_dispatch_reraises_handler_failure():
    """A failing handler must propagate so the UoW aborts the commit."""
    dispatcher = InMemoryEventDispatcher()

    async def boom(_event):
        raise RuntimeError("audit write failed")

    dispatcher.register(DomainEvent, boom)

    with pytest.raises(RuntimeError, match="audit write failed"):
        await dispatcher.dispatch([DomainEvent()])
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/infrastructure/test_event_dispatcher.py::test_dispatch_reraises_handler_failure -v`
Expected: FAIL — currently `dispatch` swallows the exception, so no `RuntimeError` is raised (`DID NOT RAISE`).

If `DomainEvent()` cannot be instantiated with no args, read `backend/app/domain/shared/events.py` and construct it with the minimal required fields; adjust the test accordingly and note it in the report.

- [ ] **Step 3: Make `dispatch` re-raise after logging**

In `event_dispatcher.py`, change the inner handler loop (lines 47-53) from swallowing to logging-and-re-raising:

```python
                    for handler in handlers:
                        try:
                            await handler(event)
                        except Exception:
                            logger.exception(
                                "Event handler failed for %s; aborting transaction",
                                type(event).__name__,
                            )
                            raise
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `cd backend && uv run pytest tests/unit/infrastructure/test_event_dispatcher.py -v`
Expected: PASS (the new test and any pre-existing tests in the file).

- [ ] **Step 5: Lint + commit**

```bash
cd backend && uvx ruff check app/infrastructure/event_dispatcher.py tests/unit/infrastructure/test_event_dispatcher.py
git add backend/app/infrastructure/event_dispatcher.py backend/tests/unit/infrastructure/test_event_dispatcher.py
git commit -m "fix(events): dispatcher re-raises handler failures so audit writes are transactional"
```

---

## Task 2: Fix IdentityClaim approve/reject crash (self._db → UoW)

**Files:**
- Modify: `backend/app/application/person/claim_handlers.py:174-178` (approve_claim) and `:214-218` (reject_claim)
- Create: `backend/tests/unit/application/__init__.py`
- Create: `backend/tests/unit/application/test_claim_command_handler.py`

**Interfaces:**
- Consumes: `ClaimCommandHandler(repo, uow)` (constructor at `claim_handlers.py:21`). `repo.add_audit(audit)` and `uow.commit()` are the existing write primitives used by `submit_claim`/`cancel_claim`/`unlink_identity`/`prelink_identity`.
- Produces: `approve_claim`/`reject_claim` write the audit row via `self._repo.add_audit(...)` and persist via `await self._uow.commit()`, returning `IdentityClaimResponse.model_validate(claim)` (no `self._db`, no post-commit `refresh`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/application/__init__.py` (empty), then create `backend/tests/unit/application/test_claim_command_handler.py`:

```python
"""Unit tests for ClaimCommandHandler approve/reject (no real DB)."""

import uuid

import pytest

from app.application.person.claim_handlers import ClaimCommandHandler


class _Person:
    def __init__(self, clan_id):
        self.created_by_clan_id = clan_id


class _Claim:
    def __init__(self, person):
        self.id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.person_id = uuid.uuid4()
        self.status = "PENDING"
        self.reviewed_by = None
        self.reviewer_note = None
        self.reviewed_at = None
        self.person = person


class _UserProfile:
    def __init__(self):
        self.person_id = None


class _FakeRepo:
    """Implements only the methods approve_claim/reject_claim call."""

    def __init__(self, claim, clan_id):
        self._claim = claim
        self._clan_id = clan_id
        self.added_audits = []
        self.added_roles = []

    async def get_claim(self, claim_id, load_person=False):
        return self._claim

    async def get_role(self, user_id, clan_id):
        return "admin"  # caller is admin of the person's clan

    async def get_user_profile(self, user_id):
        return _UserProfile()

    async def is_person_linked(self, person_id):
        return False

    async def auto_reject_other_pending_claims(self, **kwargs):
        return None

    def add_role(self, role):
        self.added_roles.append(role)

    def add_audit(self, audit):
        self.added_audits.append(audit)


class _FakeUow:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_approve_claim_uses_uow_and_writes_audit():
    clan_id = uuid.uuid4()
    claim = _Claim(_Person(clan_id))
    repo = _FakeRepo(claim, clan_id)
    uow = _FakeUow()
    handler = ClaimCommandHandler(repo, uow)

    result = await handler.approve_claim(
        claim_id=claim.id, admin_id=uuid.uuid4(), reviewer_note="ok"
    )

    assert claim.status == "APPROVED"
    assert uow.commits == 1
    assert len(repo.added_audits) == 1
    assert result.status == "APPROVED"


@pytest.mark.asyncio
async def test_reject_claim_uses_uow_and_writes_audit():
    clan_id = uuid.uuid4()
    claim = _Claim(_Person(clan_id))
    repo = _FakeRepo(claim, clan_id)
    uow = _FakeUow()
    handler = ClaimCommandHandler(repo, uow)

    result = await handler.reject_claim(
        claim_id=claim.id, admin_id=uuid.uuid4(), reviewer_note="no"
    )

    assert claim.status == "REJECTED"
    assert uow.commits == 1
    assert len(repo.added_audits) == 1
    assert result.status == "REJECTED"
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `cd backend && uv run pytest tests/unit/application/test_claim_command_handler.py -v`
Expected: FAIL — `AttributeError: 'ClaimCommandHandler' object has no attribute '_db'` (current code calls `self._db.add`/`self._db.commit`).

- [ ] **Step 3: Fix `approve_claim`**

In `claim_handlers.py`, replace the tail of `approve_claim` (lines 174-178) from:

```python
        self._db.add(audit)

        await self._db.commit()
        await self._db.refresh(claim)
        return IdentityClaimResponse.model_validate(claim)
```

to:

```python
        self._repo.add_audit(audit)

        await self._uow.commit()
        return IdentityClaimResponse.model_validate(claim)
```

- [ ] **Step 4: Fix `reject_claim`**

In `claim_handlers.py`, replace the tail of `reject_claim` (lines 214-218) from:

```python
        self._db.add(audit)

        await self._db.commit()
        await self._db.refresh(claim)
        return IdentityClaimResponse.model_validate(claim)
```

to:

```python
        self._repo.add_audit(audit)

        await self._uow.commit()
        return IdentityClaimResponse.model_validate(claim)
```

- [ ] **Step 5: Confirm no `self._db` remains in the file**

Run: `cd backend && grep -n "self._db" app/application/person/claim_handlers.py`
Expected: **no output**.

- [ ] **Step 6: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/unit/application/test_claim_command_handler.py -v`
Expected: both tests PASS.

- [ ] **Step 7: Lint + commit**

```bash
cd backend && uvx ruff check app/application/person/claim_handlers.py tests/unit/application/
git add backend/app/application/person/claim_handlers.py backend/tests/unit/application/
git commit -m "fix(claims): approve/reject persist via UoW (remove broken self._db references)"
```

---

## Task 3: Idempotent user-profile provisioning (fix registration FK violation)

**Files:**
- Modify: `backend/app/domain/auth/repository.py` — add `ensure_profile` to `AuthRepository` protocol.
- Modify: `backend/app/infrastructure/persistence/auth_repository.py` — implement `ensure_profile`.
- Modify: `backend/app/application/auth/handlers.py:94-155` — call `ensure_profile`; make create branch atomic.
- Test: `backend/tests/integration/test_auth_provisioning.py`

**Interfaces:**
- Consumes: `SqlAlchemyUnitOfWork` (`uow.session`, `uow.commit`, `uow.flush`), `Clan`, `UserClanRole`, `UserProfile` ORM models.
- Produces: `AuthRepository.ensure_profile(user_id: uuid.UUID, email: str, display_name: str | None) -> None` — idempotent get-or-create of a `user_profiles` row. After `_assign_clan_membership` runs, a `user_profiles` row exists for `user_id` before any `UserClanRole` is inserted, and the clan+profile+role for the "create" branch commit atomically.

- [ ] **Step 1: Add `ensure_profile` to the repository protocol**

In `backend/app/domain/auth/repository.py`, add to the `AuthRepository` Protocol (after `add_user_role`):

```python
    async def ensure_profile(
        self, user_id: uuid.UUID, email: str, display_name: str | None
    ) -> None:
        """Idempotently ensure a user_profiles row exists for this user."""
        ...
```

- [ ] **Step 2: Implement `ensure_profile` in the SQLAlchemy repository**

In `backend/app/infrastructure/persistence/auth_repository.py`, add this method to `SqlAlchemyAuthRepository` (after `add_user_role`). `UserProfileModel` is already imported at the top of the file:

```python
    async def ensure_profile(
        self, user_id: uuid.UUID, email: str, display_name: str | None
    ) -> None:
        existing = await self._session.get(UserProfileModel, user_id)
        if existing is not None:
            return
        self._session.add(
            UserProfileModel(
                id=user_id,
                email=email,
                display_name=display_name or email.split("@")[0],
            )
        )
        await self._session.flush()
```

- [ ] **Step 3: Call `ensure_profile` in `_assign_clan_membership` and make the create branch atomic**

In `backend/app/application/auth/handlers.py`, the `_assign_clan_membership` method currently (create branch, lines 110-131) commits the clan, then separately commits the role — and never creates a `user_profiles` row, so the `UserClanRole` FK to `user_profiles.id` fails.

Replace the **create** branch (lines 110-131) with a single atomic transaction that provisions the profile first. NOTE: the original code also calls `self._uow.track(clan)` — this is a latent second bug, because `Clan` is a plain ORM model (not a domain `AggregateRoot`), so `uow.commit()` would call the non-existent `clan.collect_events()` and crash with `AttributeError`. The replacement below **drops the `track(clan)` call** (the clan emits no domain events; it is persisted by `add_clan` + `flush`/`commit`).

```python
        if clan_action == "create":
            existing = await self._repo.get_clan_by_slug(clan_slug)
            if existing:
                raise ConflictError("auth.clan_slug_taken")

            await self._repo.ensure_profile(user_id, email, full_name)

            clan = Clan(name=clan_name, slug=clan_slug)
            self._repo.add_clan(clan)
            await self._uow.flush()  # INSERT the clan first so the role FK resolves

            role = UserClanRole(clan_id=clan.id, user_id=user_id, role="admin", is_approved=True)
            self._repo.add_user_role(role)
            await self._uow.commit()

            return RegisterResponse(
                user_id=user_id,
                email=email,
                full_name=full_name,
                clan_id=clan.id,
                is_approved=True,
                message=t("auth.clan_created"),
            )
```

Then, in the **join** branch, add the `ensure_profile` call immediately before the `UserClanRole` is created (before line 144 `role = UserClanRole(...)`):

```python
        await self._repo.ensure_profile(user_id, email, full_name)
        role = UserClanRole(clan_id=clan.id, user_id=user_id, role="viewer", is_approved=False)
        self._repo.add_user_role(role)
        await self._uow.commit()
```

This covers both `register` and `onboard_authenticated_user` (both call `_assign_clan_membership`). `ensure_profile` is idempotent, so an OAuth user whose profile was already created by the request-time `ensure_user_profile` dependency is unaffected.

- [ ] **Step 4: Write the integration test**

Create `backend/tests/integration/test_auth_provisioning.py`:

```python
"""Registration must provision a user_profiles row before inserting a membership
(regression for the FK violation where UserClanRole referenced a missing profile)."""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.auth.handlers import AuthCommandHandler
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.auth_repository import SqlAlchemyAuthRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture()
async def async_session(migrated_db_url):
    # migrated_db_url is a sync (psycopg2) DSN from the integration conftest;
    # convert to the asyncpg driver for the app's async session.
    async_dsn = migrated_db_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    engine = create_async_engine(async_dsn)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_create_clan_provisions_profile(async_session: AsyncSession):
    repo = SqlAlchemyAuthRepository(async_session)
    uow = SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    handler = AuthCommandHandler(repo, uow)

    user_id = uuid.uuid4()
    slug = f"clan-{user_id.hex[:8]}"

    resp = await handler._assign_clan_membership(
        user_id=user_id,
        email=f"{user_id.hex[:8]}@example.com",
        full_name="Người Dùng",
        clan_action="create",
        clan_name="Họ Nguyễn",
        clan_slug=slug,
    )

    assert resp.is_approved is True

    # A profile row now exists, and the membership row was inserted (no FK error).
    prof = await async_session.execute(
        sa.text("SELECT id FROM user_profiles WHERE id = :id"), {"id": user_id}
    )
    assert prof.scalar_one() == user_id
    role = await async_session.execute(
        sa.text("SELECT role FROM user_clan_roles WHERE user_id = :id"), {"id": user_id}
    )
    assert role.scalar_one() == "admin"
```

- [ ] **Step 5: Run the integration test — RED then GREEN**

Ensure Postgres is running: `cd backend && docker compose -f ../docker-compose.yml up -d pgdb` (or `cd .. && docker compose up -d pgdb`).

If you check out the pre-fix code, this test fails with an `IntegrityError` (FK violation on `user_clan_roles.user_id`). With Task 3 applied:

Run: `cd backend && uv run pytest tests/integration/test_auth_provisioning.py -v`
Expected: PASS.

- [ ] **Step 6: Confirm the SP-1 schema tests + claim/dispatcher tests still pass**

Run: `cd backend && uv run pytest tests/integration tests/unit/application tests/unit/infrastructure -v`
Expected: all PASS.

- [ ] **Step 7: Lint + commit**

```bash
cd backend && uvx ruff check app/domain/auth/repository.py app/infrastructure/persistence/auth_repository.py app/application/auth/handlers.py tests/integration/test_auth_provisioning.py
git add backend/app/domain/auth/repository.py backend/app/infrastructure/persistence/auth_repository.py backend/app/application/auth/handlers.py backend/tests/integration/test_auth_provisioning.py
git commit -m "fix(auth): provision user_profiles before membership insert; atomic clan creation"
```

---

## Done criteria (SP-2A)

- A failing event handler aborts the transaction (audit rows are transactional) — `test_dispatch_reraises_handler_failure` green.
- `ClaimCommandHandler.approve_claim`/`reject_claim` no longer reference `self._db`; both persist via the UoW — `test_claim_command_handler.py` green; `grep self._db` is empty.
- Registering (create-clan and join-clan) provisions a `user_profiles` row before the membership insert, with no FK violation — `test_auth_provisioning.py` green; clan creation commits atomically.
- All existing unit + integration tests still pass.

## Notes for the executor

- Run pytest from `backend/` (the integration conftest uses a relative `alembic.ini`).
- The integration suite needs `docker compose up -d pgdb` (postgres/postgres on :5432); the SP-1 fixture creates/drops a throwaway `family_roots_schema_test` DB per session.
- Do NOT convert claim audit writes to domain events in this plan — ADR-007 mandates the UoW path (satisfied by `add_audit` + `uow.commit`), and the rest of the file uses the same pattern. A domain-event refactor, if ever wanted, is a separate consistency task.
- Deferred from spec §2.2 to a later SP-2 plan (not a broken-flow fix): a "list my own claims" read endpoint so a user can see their own claim status. Tracked for SP-2B/SP-2 access work.
