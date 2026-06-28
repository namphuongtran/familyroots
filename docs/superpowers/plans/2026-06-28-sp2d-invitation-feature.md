# SP-2D: Clan Invitation Feature + Docs Correction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an email-targeted clan-invitation feature (admin creates an invite → gets a shareable link; invitee accepts → becomes an approved member with the pre-assigned role), coexisting with the existing self-request-join flow. Then correct the architecture docs to reflect the locked **strict clan isolation** decision.

**Architecture:** Mirror the existing clan context (no rich domain aggregate; ORM model + application handler that emits audit events via a transient `AggregateRoot`, persisted through the Unit of Work). A new `invitation` slice adds: domain events + repository port, a SQLAlchemy repository (invitation rows + the membership writes that `accept` performs), application command/query handlers, Pydantic schemas, API routes (admin create/list/revoke under `/clans/{clan_id}/invitations`; invitee accept under `/invitations/{token}/accept`), and DI wiring. The `clan_invitations` table already exists (SP-1 added `status` + `accepted_by` + a one-pending-per-`(clan_id,email)` partial unique index).

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.0 async, pytest, `uv`. Local Postgres via `docker compose up -d pgdb`.

## Global Constraints

- Python `>=3.14`; line length 100; ruff selectors per `pyproject.toml`.
- Domain layer is framework-agnostic (no FastAPI/SQLAlchemy/Pydantic). Application imports domain + ports only. SQLAlchemy lives in `infrastructure/`.
- All writes flow through `SqlAlchemyUnitOfWork`; audit is emitted as an `AuditableEvent` via a transient `AggregateRoot` (the clan-context pattern), NOT manual `AuditLog(...)` rows.
- Invitation tokens are cryptographically random (`secrets.token_urlsafe(32)`), stored in `clan_invitations.token` (unique).
- Invitation lifecycle: `status ∈ {pending, accepted, revoked, expired}`; default `pending`; `expires_at = now + INVITATION_TTL_DAYS` (config, default 7). At most one `pending` invite per `(clan_id, email)` (DB partial unique index `uq_clan_invitations_pending`).
- **Accept rules:** token must exist, be `pending`, not past `expires_at`, AND the authenticated invitee's email must equal the invite's `email` (case-insensitive). On accept: `ensure_profile` the invitee, then create/raise on existing membership, create `UserClanRole(role=<invited>, is_approved=True, approved_by=<inviter or self>, approved_at=now)` — the `user_clan_roles_approval_consistency` CHECK requires `approved_by`/`approved_at` to be non-null when `is_approved=True` (learned in SP-2A). Mark invite `accepted` + `accepted_by` + `accepted_at`. All in one transaction.
- Admin endpoints require `RequireClanRole(["admin"])` AND must guard the path `{clan_id}` against the caller's active clan (the SP-2B claims-guard pattern: `clan_id != active_clan_id → 403`).
- Coexists with self-request-join; do not remove or alter the existing membership flow.
- Strict clan isolation is the locked model — docs must stop describing persons/edges as "globally shared/visible across clans."
- **git staging discipline:** stage ONLY the files each task changes (`git add <paths>`); NEVER `git add -A` — there is unrelated user doc WIP in the working tree (Task 4 reconciles it).
- Run tests from `backend/`. Lint `uvx ruff check <paths>`. After all tasks: `uv run pytest tests/unit tests/integration -q` and `uvx ruff check .` must be clean.

---

## Files

- Create: `backend/app/domain/invitation/__init__.py`, `events.py`, `repository.py`
- Create: `backend/app/infrastructure/persistence/invitation_repository.py`
- Create: `backend/app/application/invitation/__init__.py`, `commands.py`, `handlers.py`
- Create: `backend/app/schemas/invitation.py`
- Create: `backend/app/api/v1/invitations.py`
- Modify: `backend/app/infrastructure/dependencies.py` (providers), `backend/app/api/v1/router.py` (mounts), `backend/app/core/config.py` (`INVITATION_TTL_DAYS`)
- Modify (Task 4): `docs/architecture/bounded-contexts.md`, `docs/architecture/domain-rules.md`, `backend/CLAUDE.md`, and the user's in-tree doc WIP.
- Tests: `backend/tests/integration/test_invitation_repository.py`, `backend/tests/unit/application/test_invitation_handlers.py`, `backend/tests/integration/test_invitation_accept.py`

---

## Task 1: Invitation domain events + repository (port + SQLAlchemy)

**Files:**
- Create: `backend/app/domain/invitation/__init__.py` (empty)
- Create: `backend/app/domain/invitation/events.py`
- Create: `backend/app/domain/invitation/repository.py`
- Create: `backend/app/infrastructure/persistence/invitation_repository.py`
- Create: `backend/tests/integration/test_invitation_repository.py`

**Interfaces:**
- Produces: `InvitationCreated`/`InvitationAccepted`/`InvitationRevoked` (AuditableEvent subclasses); `InvitationRepository` protocol; `SqlAlchemyInvitationRepository`. Methods consumed by Task 2's handlers:
  - `async get_pending_by_email(clan_id, email) -> ClanInvitation | None`
  - `async get_by_token(token) -> ClanInvitation | None`
  - `add_invitation(inv: ClanInvitation) -> None`
  - `async list_by_clan(clan_id) -> list[ClanInvitation]`
  - `async ensure_profile(user_id, email, display_name) -> None`  *(get-or-create user_profiles; mirrors SP-2A auth repo)*
  - `async get_user_role(user_id, clan_id) -> UserClanRole | None`
  - `add_user_role(role: UserClanRole) -> None`

- [ ] **Step 1: Create the domain events**

`backend/app/domain/invitation/__init__.py` — empty file. `backend/app/domain/invitation/events.py`:

```python
"""Domain events for the clan invitation feature."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.shared.events import AuditableEvent


@dataclass(frozen=True)
class InvitationCreated(AuditableEvent):
    email: str = ""
    invited_role: str = ""

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "invitation.create")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "clan_invitation")


@dataclass(frozen=True)
class InvitationAccepted(AuditableEvent):
    email: str = ""

    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "invitation.accept")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "clan_invitation")


@dataclass(frozen=True)
class InvitationRevoked(AuditableEvent):
    def __post_init__(self) -> None:
        if not self.action:
            object.__setattr__(self, "action", "invitation.revoke")
        if not self.resource_type:
            object.__setattr__(self, "resource_type", "clan_invitation")
```

- [ ] **Step 2: Create the repository port**

`backend/app/domain/invitation/repository.py`:

```python
"""Repository protocol for the clan invitation feature."""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class InvitationRepository(Protocol):
    async def get_pending_by_email(self, clan_id: uuid.UUID, email: str) -> Any | None:
        """Return a pending invitation for (clan_id, email), if any."""
        ...

    async def get_by_token(self, token: str) -> Any | None:
        """Return the invitation with this token, if any."""
        ...

    def add_invitation(self, invitation: Any) -> None:
        """Stage a new invitation row."""
        ...

    async def list_by_clan(self, clan_id: uuid.UUID) -> list[Any]:
        """List a clan's invitations, newest first."""
        ...

    async def ensure_profile(
        self, user_id: uuid.UUID, email: str, display_name: str | None
    ) -> None:
        """Idempotently ensure a user_profiles row exists."""
        ...

    async def get_user_role(self, user_id: uuid.UUID, clan_id: uuid.UUID) -> Any | None:
        """Existing membership for a user in a clan, if any."""
        ...

    def add_user_role(self, role: Any) -> None:
        """Stage a new user_clan_roles row."""
        ...
```

- [ ] **Step 3: Implement the SQLAlchemy repository**

`backend/app/infrastructure/persistence/invitation_repository.py`:

```python
"""SQLAlchemy implementation of the invitation repository."""

from __future__ import annotations

import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.invitation.repository import InvitationRepository
from app.models.clan_invitation import ClanInvitation
from app.models.user_clan_role import UserClanRole
from app.models.user_profile import UserProfile


class SqlAlchemyInvitationRepository(InvitationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_pending_by_email(self, clan_id: uuid.UUID, email: str) -> ClanInvitation | None:
        result = await self._session.execute(
            select(ClanInvitation).where(
                ClanInvitation.clan_id == clan_id,
                ClanInvitation.email == email,
                ClanInvitation.status == "pending",
            )
        )
        return result.scalar_one_or_none()

    async def get_by_token(self, token: str) -> ClanInvitation | None:
        result = await self._session.execute(
            select(ClanInvitation).where(ClanInvitation.token == token)
        )
        return result.scalar_one_or_none()

    def add_invitation(self, invitation: ClanInvitation) -> None:
        self._session.add(invitation)

    async def list_by_clan(self, clan_id: uuid.UUID) -> list[ClanInvitation]:
        result = await self._session.execute(
            select(ClanInvitation)
            .where(ClanInvitation.clan_id == clan_id)
            .order_by(desc(ClanInvitation.created_at))
        )
        return list(result.scalars().all())

    async def ensure_profile(
        self, user_id: uuid.UUID, email: str, display_name: str | None
    ) -> None:
        existing = await self._session.get(UserProfile, user_id)
        if existing is not None:
            return
        self._session.add(
            UserProfile(id=user_id, email=email, display_name=display_name or email.split("@")[0])
        )
        await self._session.flush()

    async def get_user_role(self, user_id: uuid.UUID, clan_id: uuid.UUID) -> UserClanRole | None:
        result = await self._session.execute(
            select(UserClanRole).where(
                UserClanRole.user_id == user_id,
                UserClanRole.clan_id == clan_id,
            )
        )
        return result.scalar_one_or_none()

    def add_user_role(self, role: UserClanRole) -> None:
        self._session.add(role)
```

- [ ] **Step 4: Write the integration test (real DB)**

`backend/tests/integration/test_invitation_repository.py` — reuse the `async_session` fixture pattern from `tests/integration/test_auth_provisioning.py`:

```python
"""SqlAlchemyInvitationRepository against a real migrated DB."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.persistence.invitation_repository import SqlAlchemyInvitationRepository
from app.models.clan_invitation import ClanInvitation


@pytest.fixture()
async def async_session(migrated_db_url):
    async_dsn = migrated_db_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    engine = create_async_engine(async_dsn)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _clan(session) -> uuid.UUID:
    cid = uuid.uuid4()
    await session.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :n, :s)"),
        {"id": cid, "n": f"c{cid.hex[:6]}", "s": f"c{cid.hex[:6]}"},
    )
    return cid


@pytest.mark.asyncio
async def test_create_and_fetch_by_token_and_pending(async_session: AsyncSession):
    repo = SqlAlchemyInvitationRepository(async_session)
    clan_id = await _clan(async_session)
    inv = ClanInvitation(
        clan_id=clan_id, email="a@example.com", role="viewer", invited_by=uuid.uuid4(),
        token="tok-123", expires_at=datetime.now(UTC) + timedelta(days=7), status="pending",
    )
    repo.add_invitation(inv)
    await async_session.commit()

    assert (await repo.get_by_token("tok-123")) is not None
    assert (await repo.get_pending_by_email(clan_id, "a@example.com")) is not None
    assert (await repo.get_pending_by_email(clan_id, "other@example.com")) is None
    assert len(await repo.list_by_clan(clan_id)) == 1


@pytest.mark.asyncio
async def test_one_pending_per_email_enforced(async_session: AsyncSession):
    repo = SqlAlchemyInvitationRepository(async_session)
    clan_id = await _clan(async_session)
    for _ in range(2):
        repo.add_invitation(
            ClanInvitation(
                clan_id=clan_id, email="dup@example.com", role="viewer", invited_by=uuid.uuid4(),
                token=f"t-{uuid.uuid4().hex}", expires_at=datetime.now(UTC) + timedelta(days=7),
                status="pending",
            )
        )
    with pytest.raises(Exception):  # unique partial index uq_clan_invitations_pending
        await async_session.commit()
```

- [ ] **Step 5: Run (RED→GREEN), lint, commit**

Run: `cd backend && docker compose -f ../docker-compose.yml up -d pgdb && uv run pytest tests/integration/test_invitation_repository.py -v`
Expected: both pass (the partial-unique test proves the DB constraint from SP-1).
Then: `uvx ruff check app/domain/invitation/ app/infrastructure/persistence/invitation_repository.py tests/integration/test_invitation_repository.py`

```bash
git add backend/app/domain/invitation/ backend/app/infrastructure/persistence/invitation_repository.py backend/tests/integration/test_invitation_repository.py
git commit -m "feat(invitation): domain events + repository (port + SQLAlchemy)"
```

---

## Task 2: Invitation application handlers + commands + schemas

**Files:**
- Create: `backend/app/application/invitation/__init__.py` (empty)
- Create: `backend/app/application/invitation/commands.py`
- Create: `backend/app/application/invitation/handlers.py`
- Create: `backend/app/schemas/invitation.py`
- Modify: `backend/app/core/config.py` (add `INVITATION_TTL_DAYS: int = 7`)
- Create: `backend/tests/unit/application/test_invitation_handlers.py`

**Interfaces:**
- Consumes: `InvitationRepository`, `SqlAlchemyUnitOfWork`, `ClanInvitation`/`UserClanRole` models, `ensure_profile`.
- Produces:
  - `InvitationCommandHandler(repo, uow)` with:
    - `async create(cmd: CreateInvitation) -> CreatedInvitation` — generates token, `expires_at`, raises `ConflictError("invitation.pending_exists")` if a pending invite exists for `(clan_id, email)`; emits `InvitationCreated`; returns `{id, token, email, role, expires_at}`.
    - `async accept(cmd: AcceptInvitation) -> AcceptedInvitation` — validates token/status/expiry/email-match; `ensure_profile`; raises `ConflictError("invitation.already_member")` if an approved role exists; creates approved `UserClanRole`; marks invite accepted; emits `InvitationAccepted`; returns `{clan_id, role}`.
    - `async revoke(cmd: RevokeInvitation) -> None` — sets `status="revoked"`; emits `InvitationRevoked`.
  - `InvitationQueryHandler(repo)` with `async list_for_clan(clan_id) -> list[dict]`.
  - Error codes: `invitation.not_found`, `invitation.not_pending`, `invitation.expired`, `invitation.email_mismatch`.

- [ ] **Step 1: Add config TTL**

In `backend/app/core/config.py`, add to `Settings` (near the scheduler settings): `INVITATION_TTL_DAYS: int = 7`.

- [ ] **Step 2: Create the command DTOs**

`backend/app/application/invitation/__init__.py` — empty. `backend/app/application/invitation/commands.py`:

```python
"""Command DTOs for the invitation use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.domain.shared.value_objects import ActorInfo


@dataclass(frozen=True)
class CreateInvitation:
    clan_id: uuid.UUID
    email: str
    role: str
    actor: ActorInfo


@dataclass(frozen=True)
class AcceptInvitation:
    token: str
    user_id: uuid.UUID
    user_email: str
    user_full_name: str


@dataclass(frozen=True)
class RevokeInvitation:
    clan_id: uuid.UUID
    invitation_id: uuid.UUID
    actor: ActorInfo
```

- [ ] **Step 3: Create the schemas**

`backend/app/schemas/invitation.py`:

```python
"""Pydantic DTOs for the invitation API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class InvitationCreateRequest(BaseModel):
    email: EmailStr
    role: str = "viewer"

    @field_validator("role")
    @classmethod
    def _role_allowed(cls, v: str) -> str:
        if v not in ("admin", "editor", "viewer"):
            raise ValueError("role must be one of: admin, editor, viewer")
        return v


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    clan_id: uuid.UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime


class InvitationCreatedResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    token: str
    expires_at: datetime
    accept_path: str  # e.g. "/api/v1/invitations/{token}/accept" — admin shares this


class InvitationAcceptRequest(BaseModel):
    # token comes from the path; body is currently empty but reserved.
    pass


class InvitationAcceptedResponse(BaseModel):
    clan_id: uuid.UUID
    role: str
    message: str
```

- [ ] **Step 4: Create the handlers**

`backend/app/application/invitation/handlers.py`:

```python
"""Invitation use-case handlers (clan-context pattern: transient AggregateRoot + events)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.application.invitation.commands import (
    AcceptInvitation,
    CreateInvitation,
    RevokeInvitation,
)
from app.core.config import settings
from app.domain.invitation.events import (
    InvitationAccepted,
    InvitationCreated,
    InvitationRevoked,
)
from app.domain.invitation.repository import InvitationRepository
from app.domain.shared.entity import AggregateRoot
from app.domain.shared.exceptions import ConflictError, EntityNotFoundError, ForbiddenError
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.models.clan_invitation import ClanInvitation
from app.models.user_clan_role import UserClanRole


class InvitationCommandHandler:
    def __init__(self, repo: InvitationRepository, uow: SqlAlchemyUnitOfWork) -> None:
        self._repo = repo
        self._uow = uow

    async def create(self, cmd: CreateInvitation) -> dict[str, Any]:
        email = cmd.email.strip().lower()
        if await self._repo.get_pending_by_email(cmd.clan_id, email):
            raise ConflictError("invitation.pending_exists")

        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(days=settings.INVITATION_TTL_DAYS)
        inv = ClanInvitation(
            clan_id=cmd.clan_id,
            email=email,
            role=cmd.role,
            invited_by=cmd.actor.user_id,
            token=token,
            expires_at=expires_at,
            status="pending",
        )
        self._repo.add_invitation(inv)
        await self._uow.flush()

        agg = AggregateRoot()
        agg.add_event(
            InvitationCreated(
                clan_id=cmd.clan_id,
                actor_id=cmd.actor.user_id,
                actor_role=cmd.actor.role,
                resource_id=inv.id,
                email=email,
                invited_role=cmd.role,
            )
        )
        self._uow.track(agg)
        await self._uow.commit()
        return {
            "id": inv.id,
            "email": email,
            "role": cmd.role,
            "token": token,
            "expires_at": expires_at,
            "accept_path": f"/api/v1/invitations/{token}/accept",
        }

    async def accept(self, cmd: AcceptInvitation) -> dict[str, Any]:
        inv = await self._repo.get_by_token(cmd.token)
        if not inv:
            raise EntityNotFoundError("invitation.not_found")
        if inv.status != "pending":
            raise ConflictError("invitation.not_pending")
        if inv.expires_at < datetime.now(UTC):
            raise ConflictError("invitation.expired")
        if inv.email.strip().lower() != cmd.user_email.strip().lower():
            raise ForbiddenError("invitation.email_mismatch")

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

        inv.status = "accepted"
        inv.accepted_by = cmd.user_id
        inv.accepted_at = datetime.now(UTC)

        agg = AggregateRoot()
        agg.add_event(
            InvitationAccepted(
                clan_id=inv.clan_id,
                actor_id=cmd.user_id,
                actor_role=inv.role,
                resource_id=inv.id,
                email=inv.email,
            )
        )
        self._uow.track(agg)
        await self._uow.commit()
        return {"clan_id": inv.clan_id, "role": inv.role}
```

The `revoke` method needs to fetch a specific invitation by id, clan-scoped. The repository port (Task 1) only has `get_by_token`, so this task ALSO adds a `get_by_id(invitation_id, clan_id)` method to BOTH `InvitationRepository` (port) and `SqlAlchemyInvitationRepository` (impl). Add `revoke` to `InvitationCommandHandler` (continues the class above):

```python
    async def revoke(self, cmd: RevokeInvitation) -> None:
        inv = await self._repo.get_by_id(cmd.invitation_id, cmd.clan_id)
        if not inv:
            raise EntityNotFoundError("invitation.not_found")
        if inv.status != "pending":
            raise ConflictError("invitation.not_pending")
        inv.status = "revoked"

        agg = AggregateRoot()
        agg.add_event(
            InvitationRevoked(
                clan_id=cmd.clan_id,
                actor_id=cmd.actor.user_id,
                actor_role=cmd.actor.role,
                resource_id=inv.id,
            )
        )
        self._uow.track(agg)
        await self._uow.commit()


class InvitationQueryHandler:
    def __init__(self, repo: InvitationRepository) -> None:
        self._repo = repo

    async def list_for_clan(self, clan_id: uuid.UUID) -> list[Any]:
        return await self._repo.list_by_clan(clan_id)
```

Add the matching `get_by_id(self, invitation_id, clan_id)` to BOTH `InvitationRepository` (port) and `SqlAlchemyInvitationRepository` (impl, from Task 1):

```python
    async def get_by_id(self, invitation_id: uuid.UUID, clan_id: uuid.UUID) -> ClanInvitation | None:
        result = await self._session.execute(
            select(ClanInvitation).where(
                ClanInvitation.id == invitation_id,
                ClanInvitation.clan_id == clan_id,
            )
        )
        return result.scalar_one_or_none()
```

- [ ] **Step 5: Write unit tests for the handlers (fakes, no DB)**

`backend/tests/unit/application/test_invitation_handlers.py`:

```python
"""Unit tests for InvitationCommandHandler with in-memory fakes."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.application.invitation.commands import (
    AcceptInvitation,
    CreateInvitation,
)
from app.application.invitation.handlers import InvitationCommandHandler
from app.domain.shared.exceptions import ConflictError, ForbiddenError
from app.domain.shared.value_objects import ActorInfo


class _Inv:
    def __init__(self, **kw):
        self.id = uuid.uuid4()
        self.status = "pending"
        self.accepted_by = None
        self.accepted_at = None
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeRepo:
    def __init__(self, pending=None, by_token=None, existing_role=None):
        self._pending = pending
        self._by_token = by_token
        self._existing_role = existing_role
        self.added_invitations = []
        self.added_roles = []
        self.ensured = []

    async def get_pending_by_email(self, clan_id, email):
        return self._pending

    async def get_by_token(self, token):
        return self._by_token

    def add_invitation(self, inv):
        self.added_invitations.append(inv)

    async def ensure_profile(self, user_id, email, display_name):
        self.ensured.append(user_id)

    async def get_user_role(self, user_id, clan_id):
        return self._existing_role

    def add_user_role(self, role):
        self.added_roles.append(role)


class _FakeUow:
    def __init__(self):
        self.commits = 0

    def track(self, agg):
        pass

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1


def _actor():
    return ActorInfo(user_id=uuid.uuid4(), role="admin")


@pytest.mark.asyncio
async def test_create_rejects_duplicate_pending():
    repo = _FakeRepo(pending=_Inv())
    handler = InvitationCommandHandler(repo, _FakeUow())
    with pytest.raises(ConflictError):
        await handler.create(
            CreateInvitation(clan_id=uuid.uuid4(), email="a@x.com", role="viewer", actor=_actor())
        )


@pytest.mark.asyncio
async def test_create_returns_token_and_path():
    repo = _FakeRepo()
    handler = InvitationCommandHandler(repo, _FakeUow())
    out = await handler.create(
        CreateInvitation(clan_id=uuid.uuid4(), email="A@X.com", role="editor", actor=_actor())
    )
    assert out["token"]
    assert out["accept_path"] == f"/api/v1/invitations/{out['token']}/accept"
    assert out["email"] == "a@x.com"  # normalized
    assert len(repo.added_invitations) == 1


@pytest.mark.asyncio
async def test_accept_email_mismatch_forbidden():
    inv = _Inv(
        clan_id=uuid.uuid4(), email="invited@x.com", role="viewer", invited_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    repo = _FakeRepo(by_token=inv)
    handler = InvitationCommandHandler(repo, _FakeUow())
    with pytest.raises(ForbiddenError):
        await handler.accept(
            AcceptInvitation(token="t", user_id=uuid.uuid4(),
                             user_email="someone-else@x.com", user_full_name="X")
        )


@pytest.mark.asyncio
async def test_accept_expired_conflict():
    inv = _Inv(
        clan_id=uuid.uuid4(), email="a@x.com", role="viewer", invited_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    repo = _FakeRepo(by_token=inv)
    handler = InvitationCommandHandler(repo, _FakeUow())
    with pytest.raises(ConflictError):
        await handler.accept(
            AcceptInvitation(token="t", user_id=uuid.uuid4(), user_email="a@x.com",
                             user_full_name="X")
        )


@pytest.mark.asyncio
async def test_accept_creates_approved_membership():
    inv = _Inv(
        clan_id=uuid.uuid4(), email="a@x.com", role="editor", invited_by=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    repo = _FakeRepo(by_token=inv)
    uow = _FakeUow()
    handler = InvitationCommandHandler(repo, uow)
    out = await handler.accept(
        AcceptInvitation(token="t", user_id=uuid.uuid4(), user_email="A@x.com",
                         user_full_name="X")
    )
    assert out["role"] == "editor"
    assert inv.status == "accepted"
    assert len(repo.added_roles) == 1
    role = repo.added_roles[0]
    assert role.is_approved is True
    assert role.approved_by == inv.invited_by and role.approved_at is not None
    assert uow.commits == 1
```

- [ ] **Step 6: Run, lint, commit**

Run: `cd backend && uv run pytest tests/unit/application/test_invitation_handlers.py -v` → all pass.
`uvx ruff check app/application/invitation/ app/schemas/invitation.py app/core/config.py app/domain/invitation/repository.py app/infrastructure/persistence/invitation_repository.py tests/unit/application/test_invitation_handlers.py`

```bash
git add backend/app/application/invitation/ backend/app/schemas/invitation.py backend/app/core/config.py backend/app/domain/invitation/repository.py backend/app/infrastructure/persistence/invitation_repository.py backend/tests/unit/application/test_invitation_handlers.py
git commit -m "feat(invitation): create/accept/revoke handlers + schemas"
```

---

## Task 3: API routes + DI wiring + router mount

**Files:**
- Create: `backend/app/api/v1/invitations.py`
- Modify: `backend/app/infrastructure/dependencies.py`
- Modify: `backend/app/api/v1/router.py`
- Create: `backend/tests/integration/test_invitation_accept.py`

**Interfaces:**
- Produces: `admin_invitations_router` (create/list/revoke under `/clans/{clan_id}/invitations`) and `user_invitations_router` (accept under `/invitations/{token}/accept`); DI providers `get_invitation_command_handler`, `get_invitation_query_handler`.

- [ ] **Step 1: DI providers**

In `dependencies.py`, add (mirroring `get_auth_command_handler`):

```python
def get_invitation_command_handler(
    db: AsyncSession = Depends(get_db),
) -> "InvitationCommandHandler":
    from app.application.invitation.handlers import InvitationCommandHandler
    from app.infrastructure.event_dispatcher import create_event_dispatcher
    from app.infrastructure.persistence.invitation_repository import (
        SqlAlchemyInvitationRepository,
    )
    from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

    repo = SqlAlchemyInvitationRepository(db)
    uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
    return InvitationCommandHandler(repo, uow)


def get_invitation_query_handler(
    db: AsyncSession = Depends(get_db),
) -> "InvitationQueryHandler":
    from app.application.invitation.handlers import InvitationQueryHandler
    from app.infrastructure.persistence.invitation_repository import (
        SqlAlchemyInvitationRepository,
    )

    return InvitationQueryHandler(SqlAlchemyInvitationRepository(db))
```

(Add `InvitationCommandHandler, InvitationQueryHandler` to the `TYPE_CHECKING` import block if the file uses one for annotations.)

- [ ] **Step 2: Routes**

`backend/app/api/v1/invitations.py`:

```python
"""Clan invitation endpoints — admin create/list/revoke + invitee accept."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.invitation.commands import (
    AcceptInvitation,
    CreateInvitation,
    RevokeInvitation,
)
from app.application.invitation.handlers import InvitationCommandHandler, InvitationQueryHandler
from app.core.permissions import RequireClanRole
from app.core.security import get_current_clan_id, get_current_user
from app.domain.shared.value_objects import ActorInfo
from app.infrastructure.dependencies import (
    get_invitation_command_handler,
    get_invitation_query_handler,
)
from app.schemas.auth import UserProfile
from app.schemas.invitation import (
    InvitationAcceptedResponse,
    InvitationCreatedResponse,
    InvitationCreateRequest,
    InvitationResponse,
)
from app.services.translator import t

admin_invitations_router = APIRouter()
user_invitations_router = APIRouter()


@admin_invitations_router.post("", response_model=InvitationCreatedResponse, status_code=201)
async def create_invitation(
    clan_id: uuid.UUID,
    body: InvitationCreateRequest,
    user: UserProfile = Depends(RequireClanRole(["admin"])),
    active_clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: InvitationCommandHandler = Depends(get_invitation_command_handler),
) -> Any:
    if clan_id != active_clan_id:
        raise HTTPException(status_code=403, detail="Path clan does not match your active clan")
    out = await handler.create(
        CreateInvitation(
            clan_id=clan_id, email=body.email, role=body.role,
            actor=ActorInfo(user_id=user.id, role="admin"),
        )
    )
    return out


@admin_invitations_router.get("")
async def list_invitations(
    clan_id: uuid.UUID,
    user: UserProfile = Depends(RequireClanRole(["admin"])),
    active_clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: InvitationQueryHandler = Depends(get_invitation_query_handler),
) -> dict[str, Any]:
    if clan_id != active_clan_id:
        raise HTTPException(status_code=403, detail="Path clan does not match your active clan")
    invites = await handler.list_for_clan(clan_id)
    return {"data": [InvitationResponse.model_validate(i).model_dump() for i in invites]}


@admin_invitations_router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    clan_id: uuid.UUID,
    invitation_id: uuid.UUID,
    user: UserProfile = Depends(RequireClanRole(["admin"])),
    active_clan_id: uuid.UUID = Depends(get_current_clan_id),
    handler: InvitationCommandHandler = Depends(get_invitation_command_handler),
) -> None:
    if clan_id != active_clan_id:
        raise HTTPException(status_code=403, detail="Path clan does not match your active clan")
    await handler.revoke(
        RevokeInvitation(
            clan_id=clan_id, invitation_id=invitation_id,
            actor=ActorInfo(user_id=user.id, role="admin"),
        )
    )


@user_invitations_router.post("/{token}/accept", response_model=InvitationAcceptedResponse)
async def accept_invitation(
    token: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    handler: InvitationCommandHandler = Depends(get_invitation_command_handler),
) -> Any:
    out = await handler.accept(
        AcceptInvitation(
            token=token,
            user_id=uuid.UUID(current_user["sub"]),
            user_email=current_user.get("email", ""),
            user_full_name=current_user.get("user_metadata", {}).get("full_name", ""),
        )
    )
    return InvitationAcceptedResponse(
        clan_id=out["clan_id"], role=out["role"], message=t("invitation.accepted")
    )
```

- [ ] **Step 3: Mount in router.py**

In `app/api/v1/router.py`, add imports + includes (mirroring the claims mounts):

```python
from app.api.v1.invitations import admin_invitations_router, user_invitations_router
```
```python
api_v1_router.include_router(
    admin_invitations_router, prefix="/clans/{clan_id}/invitations", tags=["invitations"]
)
api_v1_router.include_router(
    user_invitations_router, prefix="/invitations", tags=["invitations"]
)
```

Also add the `invitation.accepted` translation key — check `app/services/translator.py` / the i18n files for how keys are defined and add a key `invitation.accepted` (e.g. "Invitation accepted") in the same place existing `auth.*` keys live. If the translator falls back to the key string when missing, this is optional but preferred; do it to match the codebase convention.

- [ ] **Step 4: Accept integration test (real DB, exercises the full handler→repo→DB path)**

`backend/tests/integration/test_invitation_accept.py` — seed a clan + a pending invitation, then drive `InvitationCommandHandler.accept` and assert an approved `user_clan_roles` row exists and the invite is `accepted`:

```python
"""Accepting an invitation creates an approved membership (real DB)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.invitation.commands import AcceptInvitation
from app.application.invitation.handlers import InvitationCommandHandler
from app.infrastructure.event_dispatcher import create_event_dispatcher
from app.infrastructure.persistence.invitation_repository import SqlAlchemyInvitationRepository
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture()
async def async_session(migrated_db_url):
    async_dsn = migrated_db_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    engine = create_async_engine(async_dsn)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_accept_invitation_grants_approved_membership(async_session: AsyncSession):
    clan_id, inviter, token = uuid.uuid4(), uuid.uuid4(), "tok-accept"
    await async_session.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'C', :s)"),
        {"id": clan_id, "s": f"c{clan_id.hex[:6]}"},
    )
    await async_session.execute(
        sa.text(
            "INSERT INTO clan_invitations (id, clan_id, email, role, invited_by, token, "
            "expires_at, status) VALUES (:id, :c, :e, 'editor', :ib, :t, :exp, 'pending')"
        ),
        {"id": uuid.uuid4(), "c": clan_id, "e": "invitee@example.com", "ib": inviter,
         "t": token, "exp": datetime.now(UTC) + timedelta(days=7)},
    )
    await async_session.commit()

    repo = SqlAlchemyInvitationRepository(async_session)
    uow = SqlAlchemyUnitOfWork(async_session, create_event_dispatcher(async_session))
    handler = InvitationCommandHandler(repo, uow)

    invitee = uuid.uuid4()
    out = await handler.accept(
        AcceptInvitation(token=token, user_id=invitee,
                         user_email="invitee@example.com", user_full_name="Invitee")
    )
    assert out["role"] == "editor"

    role = await async_session.execute(
        sa.text("SELECT role, is_approved FROM user_clan_roles WHERE user_id = :u"),
        {"u": invitee},
    )
    r = role.first()
    assert r.role == "editor" and r.is_approved is True
    inv_status = await async_session.execute(
        sa.text("SELECT status FROM clan_invitations WHERE token = :t"), {"t": token}
    )
    assert inv_status.scalar_one() == "accepted"
```

- [ ] **Step 5: Run, lint, commit**

Run: `cd backend && uv run pytest tests/integration/test_invitation_accept.py -v && uv run python -c "import app.api.v1.router"` → pass + import OK.
`uvx ruff check app/api/v1/invitations.py app/infrastructure/dependencies.py app/api/v1/router.py tests/integration/test_invitation_accept.py`

```bash
git add backend/app/api/v1/invitations.py backend/app/infrastructure/dependencies.py backend/app/api/v1/router.py backend/tests/integration/test_invitation_accept.py
git commit -m "feat(invitation): admin create/list/revoke + invitee accept routes"
```

---

## Task 4: Docs correction (strict isolation) + reconcile in-tree doc WIP

**Files:**
- Modify: `docs/architecture/bounded-contexts.md`, `docs/architecture/domain-rules.md`, `backend/CLAUDE.md`
- (the above are currently uncommitted user WIP in the working tree — this task edits + commits them properly)

**Interfaces:** documentation only; no code.

- [ ] **Step 1: Correct the visibility model in the architecture docs**

In `docs/architecture/bounded-contexts.md` and `docs/architecture/domain-rules.md`, replace statements that describe `person` and relationship edges as "globally shared" / "visible across clans" with the strict-isolation model: persons and edges are **clan-isolated** — a clan reads only its own persons and the edges it created (`created_by_clan_id`); cross-clan reads return not-found. Keep `created_by_clan_id` described as the write+read scoping key. Remove or rewrite the "person vs user globally shared" framing to "person is distinct from the authenticated user, and is clan-scoped." Add a short "Invitation" note to the clan/auth context describing the new flow (admin creates email-targeted token → invitee accepts → approved membership), coexisting with self-request-join.

- [ ] **Step 2: Fix the RLS claim in backend/CLAUDE.md**

In `backend/CLAUDE.md`, the "Clan isolation and auth" section claims "Supabase RLS at the DB level enforces row visibility by clan_id." Change it to reflect reality: clan isolation is enforced in the application/repository layer (every clan-scoped read takes `clan_id`); RLS is a planned defense-in-depth addition (SP-3), not yet active.

- [ ] **Step 3: Sanity-check the docs reference real code**

Run: `cd "$(git rev-parse --show-toplevel)" && grep -rn "globally shared\|globally-shared\|visible across clans\|RLS enforces" docs/ backend/CLAUDE.md`
Expected: no remaining stale claims (or each remaining hit is in an ADR explicitly describing history, which you should leave with a "superseded by strict isolation" note).

- [ ] **Step 4: Commit (docs only — stage the specific doc files)**

```bash
cd "$(git rev-parse --show-toplevel)"
git add docs/architecture/bounded-contexts.md docs/architecture/domain-rules.md backend/CLAUDE.md
git commit -m "docs: correct visibility model to strict clan isolation; add invitation flow"
```

NOTE: other untracked docs (`docs/contracts/domain-events-catalog.md`, `docs/decisions/006`, `007`, modified READMEs) are pre-existing user WIP. Only touch/commit the three files this task edits; leave the rest for the user unless they instruct otherwise. If asked to also commit those, do so as a separate `docs:` commit.

---

## Done criteria (SP-2D)

- Invitation repository round-trips against a real DB; the one-pending-per-`(clan,email)` constraint is enforced — `test_invitation_repository.py` green.
- Create rejects duplicate pending invites and returns a token + accept path; accept enforces token/status/expiry/email-match and grants an approved membership with `approved_by`/`approved_at` — `test_invitation_handlers.py` + `test_invitation_accept.py` green.
- Admin routes require `admin` AND guard the path clan; accept route reads the invitee's identity from the JWT; routes mounted; `import app.api.v1.router` OK.
- Architecture docs + `backend/CLAUDE.md` reflect strict isolation; no stale "globally shared"/"RLS enforces" claims.
- Full `tests/unit` + `tests/integration` suite passes; `ruff check .` clean.

## Notes for the executor

- Run pytest from `backend/`; integration tasks need `docker compose up -d pgdb`.
- `git add <specific paths>` only — never `git add -A` (user doc WIP is in the tree).
- The `accept` flow reuses the SP-2A learning: an approved `UserClanRole` MUST set `approved_by` + `approved_at` (DB CHECK `user_clan_roles_approval_consistency`).
- After all tasks, run the repo-wide suite + `ruff check .` to catch anything outside each task's files (SP-2B lesson).
