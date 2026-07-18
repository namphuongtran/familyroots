# Deactivation Invariant (A1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `user_profiles.is_active = false` an invariant enforced on every authenticated request (one chokepoint in `get_current_user`), at login, and in notification fan-out — closing H1 from `docs/architecture/backend-review-2026-07-18.md`.

**Architecture:** Option A per the approved spec (`docs/superpowers/specs/2026-07-18-deactivation-invariant-design.md`): the gate moves INTO `get_current_user` (every authed route inherits it by construction); the two duplicate checks in `ensure_user_profile` / `get_current_clan_id` are then removed (single source). `login` gets a handler-level gate via a new `AuthQueryPort.is_account_active`. `refresh` is intentionally NOT gated (DB-free service by design; tokens are inert against the gated API). `send_to_clan` filters deactivated members.

**Tech Stack:** FastAPI dependencies, SQLAlchemy async, real-Postgres integration tests with real RS256 JWT verification (JWKS-cache injection pattern from `tests/integration/test_auth_http_flow.py`).

## Global Constraints

- Only an **explicit `is_active = False`** blocks; a missing profile row (`None`) must pass (first-login provisioning). Never `if not is_active`.
- Error is the EXISTING code: 403, envelope `{"error": {"code": "account_deactivated", ...}}` — no new i18n keys (present in all 4 locales at `app/i18n/*.json:134`).
- New tests must NOT override `get_current_user` via `dependency_overrides` — they exist to exercise the real chokepoint. Only `get_db` (and, for the login test, `get_identity_provider`) may be overridden.
- Application layer raises `ForbiddenError` from `app.domain.shared.exceptions` (match the existing import block in `app/application/auth/handlers.py:31`); `app/core/security.py` keeps using `app.core.exceptions.ForbiddenError` as it does today.
- RED-first: run each new test and confirm the exact expected failure before implementing.
- Full quality gate before claiming done: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.
- Rate-limit budget: the new test module's app instance shares a 20 req/min/IP bucket across `/api/v1/auth` + `/api/v1/invitations` — keep total requests on those prefixes under ~10 in the module.

---

### Task 1: Chokepoint gate in `get_current_user` (RED → GREEN)

**Files:**
- Create: `backend/tests/integration/test_deactivation_invariant.py`
- Modify: `backend/app/core/security.py` (function `get_current_user`, currently lines 99-105)

**Interfaces:**
- Produces: `get_current_user` gains parameter `db: AsyncSession = Depends(get_db)`; behavior contract "explicit False → 403 account_deactivated, None → pass" that Tasks 2–3 rely on.

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/integration/test_deactivation_invariant.py`:

```python
"""H1 (review 2026-07-18): deactivation must be an invariant, not a per-route accident.

Drives the previously-BYPASSED routes over HTTP with REAL RS256 JWTs (the JWKS
cache is primed with a test keypair so ``verify_supabase_token`` runs for real)
and a real migrated DB. ``get_current_user`` is NOT dependency-overridden — that
is the point: these tests exercise the chokepoint gate itself. A revert of the
gate in ``get_current_user`` fails every 403 assertion here.

Rate-limit budget: this module's app instance shares the 20 req/min/IP bucket on
/api/v1/auth + /api/v1/invitations — keep total requests on those prefixes low.
"""

import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwk, jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.security as security_module
from app.core.database import get_db
from app.main import create_app

pytestmark = pytest.mark.integration

_KID = "deact-test-key"


@pytest.fixture(scope="module")
def rsa_keys() -> dict[str, Any]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    public_jwk = jwk.construct(public_pem, "RS256").to_dict()
    public_jwk.update({"kid": _KID, "use": "sig", "alg": "RS256"})
    return {"private_pem": private_pem, "jwks": {"keys": [public_jwk]}}


@pytest.fixture(scope="module")
def jwks_cache(rsa_keys: dict[str, Any]) -> Iterator[None]:
    old_cache, old_time = security_module._jwks_cache, security_module._jwks_cache_time
    security_module._jwks_cache = rsa_keys["jwks"]
    security_module._jwks_cache_time = time.monotonic()
    yield
    security_module._jwks_cache, security_module._jwks_cache_time = old_cache, old_time


def _issuer() -> str:
    return f"{security_module.settings.SUPABASE_URL.rstrip('/')}/auth/v1"  # type: ignore[attr-defined]


def _mint(private_pem: str, user_id: uuid.UUID, email: str) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "iss": _issuer(),
        "iat": now,
        "exp": now + timedelta(hours=1),
        "user_metadata": {"full_name": "Deact Test"},
    }
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": _KID})


@pytest.fixture(scope="module")
def client(migrated_db_url: str, jwks_cache: None) -> Iterator[TestClient]:
    app = create_app()
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    yield TestClient(app)
    engine.sync_engine.dispose()


def _sync_engine(dsn: str) -> sa.Engine:
    return sa.create_engine(dsn.replace("+asyncpg", ""))


def _seed_profile(dsn: str, *, active: bool) -> tuple[uuid.UUID, str]:
    """Insert a user_profiles row; return (user_id, email)."""
    user_id = uuid.uuid4()
    email = f"deact-{user_id.hex[:8]}@ex.com"
    eng = _sync_engine(dsn)
    try:
        with eng.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name, is_active) "
                    "VALUES (:u, :e, 'U', :act)"
                ),
                {"u": user_id, "e": email, "act": active},
            )
    finally:
        eng.dispose()
    return user_id, email


def _seed_invitation(dsn: str, *, email: str) -> tuple[str, uuid.UUID]:
    """Clan + admin inviter + pending invitation for `email`; return (token, clan_id)."""
    clan_id, inviter_id = uuid.uuid4(), uuid.uuid4()
    token = f"tok-{uuid.uuid4().hex}"
    eng = _sync_engine(dsn)
    try:
        with eng.begin() as conn:
            conn.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:c, 'C', :sl)"),
                {"c": clan_id, "sl": f"c-{clan_id.hex[:8]}"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name) "
                    "VALUES (:u, :e, 'Inviter')"
                ),
                {"u": inviter_id, "e": f"inv-{inviter_id.hex[:8]}@ex.com"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO user_clan_roles (user_id, clan_id, role, is_approved, "
                    "approved_by, approved_at) VALUES (:u, :c, 'admin', true, :u, now())"
                ),
                {"u": inviter_id, "c": clan_id},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO clan_invitations (id, clan_id, email, role, status, "
                    "invited_by, token, expires_at) VALUES (:i, :c, :e, 'viewer', "
                    "'pending', :inv, :t, now() + interval '7 days')"
                ),
                {"i": uuid.uuid4(), "c": clan_id, "e": email, "inv": inviter_id, "t": token},
            )
    finally:
        eng.dispose()
    return token, clan_id


def _membership_exists(dsn: str, user_id: uuid.UUID, clan_id: uuid.UUID) -> bool:
    eng = _sync_engine(dsn)
    try:
        with eng.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT 1 FROM user_clan_roles WHERE user_id = :u AND clan_id = :c"
                ),
                {"u": user_id, "c": clan_id},
            ).first()
        return row is not None
    finally:
        eng.dispose()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_deactivated(resp: Any) -> None:
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "account_deactivated"


def test_deactivated_403_on_auth_me(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    user_id, email = _seed_profile(migrated_db_url, active=False)
    resp = client.get("/api/v1/auth/me", headers=_auth(_mint(rsa_keys["private_pem"], user_id, email)))
    _assert_deactivated(resp)


def test_deactivated_403_on_me_clans(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    user_id, email = _seed_profile(migrated_db_url, active=False)
    resp = client.get("/api/v1/me/clans", headers=_auth(_mint(rsa_keys["private_pem"], user_id, email)))
    _assert_deactivated(resp)


def test_deactivated_403_on_onboard(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    user_id, email = _seed_profile(migrated_db_url, active=False)
    resp = client.post(
        "/api/v1/auth/onboard",
        headers=_auth(_mint(rsa_keys["private_pem"], user_id, email)),
        json={
            "clan_action": "create",
            "clan_name": "Deact Clan",
            "clan_slug": f"deact-{user_id.hex[:8]}",
        },
    )
    _assert_deactivated(resp)


def test_deactivated_cannot_accept_invitation(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    """The privilege escalation from the review: a deactivated user must not be
    able to convert a pending invitation into an approved membership."""
    user_id, email = _seed_profile(migrated_db_url, active=False)
    token, clan_id = _seed_invitation(migrated_db_url, email=email)
    resp = client.post(
        f"/api/v1/invitations/{token}/accept",
        headers=_auth(_mint(rsa_keys["private_pem"], user_id, email)),
    )
    _assert_deactivated(resp)
    assert not _membership_exists(migrated_db_url, user_id, clan_id)


def test_active_user_positive_control(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    """Same wiring, active profile → the gate must NOT fire."""
    user_id, email = _seed_profile(migrated_db_url, active=True)
    resp = client.get("/api/v1/auth/me", headers=_auth(_mint(rsa_keys["private_pem"], user_id, email)))
    assert resp.status_code == 200, resp.text


def test_missing_profile_is_not_deactivated(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    """None != False: a brand-new account (no profile row yet) must pass the
    chokepoint so first-login provisioning keeps working."""
    user_id = uuid.uuid4()  # never seeded
    resp = client.get(
        "/api/v1/me/clans",
        headers=_auth(_mint(rsa_keys["private_pem"], user_id, f"new-{user_id.hex[:8]}@ex.com")),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []
```

- [ ] **Step 2: Run the new tests — verify they FAIL for the right reason**

Run: `cd backend && uv run pytest tests/integration/test_deactivation_invariant.py -v`
Expected: the four `deactivated_*` tests FAIL (routes return 200/201, not 403 — the bypass is real); the two controls PASS.

- [ ] **Step 3: Implement the chokepoint gate**

In `backend/app/core/security.py`, replace `get_current_user` (lines 99-105) with:

```python
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """FastAPI dependency — extract and validate JWT from Authorization header.

    Also enforces the account-deactivation invariant (H1, review 2026-07-18):
    deactivation lives only in our DB — the Supabase JWT stays valid — so it is
    gated HERE, the single chokepoint every authenticated route inherits by
    construction. Only an explicit ``is_active = False`` blocks; a missing
    profile row (``None``) is a brand-new account that ``ensure_user_profile``
    will provision on this same request.
    """
    if credentials is None:
        raise AuthenticationError("missing_token")
    payload = await verify_supabase_token(credentials.credentials)
    is_account_active = await db.scalar(
        select(UserProfile.is_active).where(UserProfile.id == uuid.UUID(payload["sub"]))
    )
    if is_account_active is False:
        raise ForbiddenError("account_deactivated")
    return payload
```

All names (`select`, `get_db`, `AsyncSession`, `UserProfile`, `ForbiddenError`) are already imported in this module — add nothing.

- [ ] **Step 4: Run the new tests — verify all PASS**

Run: `cd backend && uv run pytest tests/integration/test_deactivation_invariant.py -v`
Expected: 6/6 PASS.

- [ ] **Step 5: Run adjacent suites (regression check)**

Run: `cd backend && uv run pytest tests/integration/test_auth_http_flow.py tests/integration/test_account_deactivation.py tests/unit/api -q`
Expected: PASS (the duplicate checks are still in place; the chokepoint is additive at this point). If a unit test calls `get_current_user(...)` directly without `db`, update that call site to pass a session/mock — do not weaken the gate.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/integration/test_deactivation_invariant.py backend/app/core/security.py
git commit -m "fix(auth): enforce account deactivation at the get_current_user chokepoint (H1)"
```

---

### Task 2: Remove the duplicate checks — single source of truth

**Files:**
- Modify: `backend/app/core/security.py` (`ensure_user_profile` lines ~181-185, `get_current_clan_id` lines ~224-234)
- Modify: `backend/tests/integration/test_account_deactivation.py`

**Interfaces:**
- Consumes: Task 1's chokepoint (`get_current_user` gates `is_active`).
- Produces: `ensure_user_profile` and `get_current_clan_id` no longer duplicate the gate; direct-call tests of those functions no longer see `account_deactivated`.

- [ ] **Step 1: Remove the duplicate in `ensure_user_profile`**

Delete these lines (currently `security.py:181-185`):

```python
    # A deactivated account is authenticated (its Supabase JWT is still valid) but must
    # not be allowed to act — deactivation lives only in our DB, so it is enforced here,
    # the single chokepoint that loads the local profile.
    if not profile.is_active:
        raise ForbiddenError("account_deactivated")
```

and replace with the single comment line:

```python
    # Deactivation (is_active=False) is enforced upstream in get_current_user — the
    # chokepoint every authenticated route inherits. No duplicate check here.
```

- [ ] **Step 2: Remove the duplicate in `get_current_clan_id`**

Delete the block (currently `security.py:224-234`):

```python
    # Block a deactivated account up front — this path authenticates via the JWT and
    # never loads the profile (unlike ensure_user_profile), so the is_active gate must
    # be applied here for every clan-scoped request. Only an explicit False is a
    # deactivation; a missing profile row (None) means "no account/membership yet" and
    # falls through to the membership check below, which yields the accurate
    # no_approved_clan_membership rather than a misleading account_deactivated.
    is_account_active = await db.scalar(
        select(UserProfile.is_active).where(UserProfile.id == user_id)
    )
    if is_account_active is False:
        raise ForbiddenError("account_deactivated")
```

and replace with the single comment line:

```python
    # Deactivation (is_active=False) is enforced upstream in get_current_user — the
    # chokepoint every authenticated route inherits. No duplicate check here.
```

If `UserProfile` becomes an unused import after this edit, keep it only if still used elsewhere in the module (it is — `ensure_user_profile` returns it); ruff will tell you.

- [ ] **Step 3: Update the pinning tests to the new architecture**

Replace the CONTENT of `backend/tests/integration/test_account_deactivation.py` with:

```python
"""L3: a deactivated account (user_profiles.is_active = False) cannot act.

Since the H1 fix (review 2026-07-18) the gate lives in ONE place —
``get_current_user`` — and is covered over HTTP (real JWT, real routes) by
``test_deactivation_invariant.py``. This file keeps the layer-level behaviors
that remain true of the clan-resolution path itself: an active user resolves
their clan, and a MISSING profile row is reported as the accurate
``no_approved_clan_membership``, never ``account_deactivated``.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.exceptions import ForbiddenError
from app.core.security import get_current_clan_id

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture()
async def async_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed(s: AsyncSession, *, active: bool) -> tuple[uuid.UUID, uuid.UUID]:
    """Create an (active clan, user with an approved membership) and return their ids."""
    clan_id, user_id = uuid.uuid4(), uuid.uuid4()
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:c, 'C', :sl)"),
        {"c": clan_id, "sl": f"c-{clan_id.hex[:8]}"},
    )
    await s.execute(
        sa.text(
            "INSERT INTO user_profiles (id, email, display_name, is_active) "
            "VALUES (:u, :e, 'U', :act)"
        ),
        {"u": user_id, "e": f"u-{user_id.hex[:8]}@ex.com", "act": active},
    )
    await s.execute(
        sa.text(
            "INSERT INTO user_clan_roles (user_id, clan_id, role, is_approved, approved_by, "
            "approved_at) VALUES (:u, :c, 'editor', true, :u, now())"
        ),
        {"u": user_id, "c": clan_id},
    )
    await s.commit()
    return clan_id, user_id


async def test_active_user_resolves_clan(async_session: AsyncSession) -> None:
    """Positive control: an active user with an approved membership resolves the clan."""
    clan_id, user_id = await _seed(async_session, active=True)
    resolved = await get_current_clan_id(
        current_user={"sub": str(user_id)},
        db=async_session,
        x_current_clan_id=str(clan_id),
    )
    assert resolved == clan_id


async def test_no_profile_is_not_treated_as_deactivated(async_session: AsyncSession) -> None:
    """A user with no profile row must NOT be reported as deactivated — they fall
    through to the accurate no_approved_clan_membership. Only an explicit
    is_active=False (enforced upstream in get_current_user) is a deactivation."""
    with pytest.raises(ForbiddenError, match="no_approved_clan_membership"):
        await get_current_clan_id(
            current_user={"sub": str(uuid.uuid4())},  # never onboarded → no profile
            db=async_session,
            x_current_clan_id=None,
        )
```

(The two removed direct-call tests are superseded by the HTTP-level chokepoint tests in `test_deactivation_invariant.py`, which exercise the real dependency chain those direct calls can no longer reach.)

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && uv run pytest -q`
Expected: PASS. If any other test pinned `account_deactivated` from the removed sites, first check whether it goes through the dependency chain (then it still passes via the chokepoint); only rewrite tests that call `ensure_user_profile`/`get_current_clan_id` as plain functions expecting the deactivation raise.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/security.py backend/tests/integration/test_account_deactivation.py
git commit -m "refactor(auth): single-source the deactivation gate; drop duplicate checks"
```

---

### Task 3: Login gate via `AuthQueryPort.is_account_active`

**Files:**
- Modify: `backend/app/domain/auth/repository.py` (`AuthQueryPort` protocol, ~line 70)
- Modify: `backend/app/infrastructure/persistence/auth_repository.py` (`SqlAlchemyAuthQueryPort`, ~line 96)
- Modify: `backend/app/application/auth/handlers.py` (`login`, ~line 314; import block ~line 31)
- Modify: `backend/tests/integration/test_deactivation_invariant.py` (add login tests)

**Interfaces:**
- Consumes: existing `AuthQueryPort` wiring (login handler already holds `self._query_port`).
- Produces: `async def is_account_active(self, user_id: uuid.UUID) -> bool | None` on the port; login raises domain `ForbiddenError("account_deactivated")` for explicit False.

- [ ] **Step 1: Write the failing login tests**

Append to `backend/tests/integration/test_deactivation_invariant.py`:

```python
# ── Login gate (handler-level; no JWT dependency runs on /auth/login) ──────────

from app.domain.auth.identity_provider import (  # noqa: E402
    AuthenticatedIdentity,
    AuthTokens,
    IdentityAuthError,
)
from app.infrastructure.dependencies import get_identity_provider  # noqa: E402


class _LoginStub:
    """sign_in-only identity stub — the login-gate tests need no other provider op."""

    def __init__(self, user_id: uuid.UUID, email: str, password: str) -> None:
        self._user_id, self._email, self._password = user_id, email, password

    async def sign_in(self, *, email: str, password: str) -> AuthenticatedIdentity:
        if email != self._email or password != self._password:
            raise IdentityAuthError("invalid credentials")
        return AuthenticatedIdentity(
            user_id=str(self._user_id),
            email=email,
            full_name="Deact Login",
            tokens=AuthTokens(
                access_token="stub-access", refresh_token="stub-refresh", expires_in=3600
            ),
        )


def _login(client: TestClient, stub: _LoginStub, email: str, password: str) -> Any:
    original = client.app.dependency_overrides.get(get_identity_provider)  # type: ignore[attr-defined]
    client.app.dependency_overrides[get_identity_provider] = lambda: stub  # type: ignore[attr-defined]
    try:
        return client.post("/api/v1/auth/login", json={"email": email, "password": password})
    finally:
        if original is not None:
            client.app.dependency_overrides[get_identity_provider] = original  # type: ignore[attr-defined]
        else:
            client.app.dependency_overrides.pop(get_identity_provider, None)  # type: ignore[attr-defined]


def test_deactivated_login_rejected_no_tokens(
    client: TestClient, migrated_db_url: str
) -> None:
    """Valid credentials + deactivated profile → 403, and the body must contain
    neither tokens nor profile data."""
    user_id, email = _seed_profile(migrated_db_url, active=False)
    resp = _login(client, _LoginStub(user_id, email, "pw-1"), email, "pw-1")
    _assert_deactivated(resp)
    assert "access_token" not in resp.text
    assert "refresh_token" not in resp.text


def test_active_login_positive_control(client: TestClient, migrated_db_url: str) -> None:
    user_id, email = _seed_profile(migrated_db_url, active=True)
    resp = _login(client, _LoginStub(user_id, email, "pw-2"), email, "pw-2")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["access_token"] == "stub-access"
```

If `AuthenticatedIdentity` requires more constructor fields (check its dataclass in
`app/domain/auth/identity_provider.py`), supply them the same way
`tests/integration/test_auth_http_flow.py`'s stub does — do not change the dataclass.

- [ ] **Step 2: Run — verify the deactivated test FAILS (login returns 200 with tokens)**

Run: `cd backend && uv run pytest tests/integration/test_deactivation_invariant.py -k login -v`
Expected: `test_deactivated_login_rejected_no_tokens` FAILS (200 != 403); positive control PASSES.

- [ ] **Step 3: Add the port method**

In `backend/app/domain/auth/repository.py`, inside `class AuthQueryPort(Protocol)` after `get_login_profile`:

```python
    async def is_account_active(self, user_id: uuid.UUID) -> bool | None:
        """``user_profiles.is_active`` for this user; ``None`` when no profile row exists."""
        ...
```

- [ ] **Step 4: Implement in the adapter**

In `backend/app/infrastructure/persistence/auth_repository.py`, add to `SqlAlchemyAuthQueryPort`:

```python
    async def is_account_active(self, user_id: uuid.UUID) -> bool | None:
        return await self._session.scalar(
            select(UserProfileModel.is_active).where(UserProfileModel.id == user_id)
        )
```

- [ ] **Step 5: Gate the login handler**

In `backend/app/application/auth/handlers.py::login`, immediately after
`user_id = uuid.UUID(identity.user_id)` (before `get_login_profile`):

```python
        # H1 chokepoint parity: login returns fresh tokens plus profile/clan data —
        # a deactivated account gets neither. Only an explicit False blocks (a
        # missing profile row is a brand-new account). /auth/refresh is intentionally
        # NOT gated: AuthSessionService is DB-free by design and refreshed tokens are
        # inert against the API (get_current_user 403s every authenticated request).
        if await self._query_port.is_account_active(user_id) is False:
            raise ForbiddenError("account_deactivated")
```

Add `ForbiddenError` to the existing `from app.domain.shared.exceptions import (...)` block at line ~31 if not already imported.

- [ ] **Step 6: Fix any unit-test fakes of `AuthQueryPort`**

Run: `grep -rn "AuthQueryPort\|get_login_profile" backend/tests/unit | grep -v __pycache__`
Any fake used by login unit tests gains `async def is_account_active(self, user_id): return True` (or `None`) so the gate passes for existing scenarios. Do not silence the gate any other way.

- [ ] **Step 7: Run — verify all green**

Run: `cd backend && uv run pytest tests/integration/test_deactivation_invariant.py tests/unit -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/domain/auth/repository.py backend/app/infrastructure/persistence/auth_repository.py backend/app/application/auth/handlers.py backend/tests/integration/test_deactivation_invariant.py
git commit -m "fix(auth): reject deactivated accounts at login (no tokens, no profile)"
```

---

### Task 4: `send_to_clan` excludes deactivated members

**Files:**
- Modify: `backend/app/services/notification.py` (the member SELECT in `send_to_clan`, ~line 116)
- Modify: `backend/tests/integration/test_send_to_clan.py`

**Interfaces:**
- Consumes: existing `send_to_clan(clan_id, title_key, body_key, db, ...) -> tuple[int, int]`.
- Produces: fan-out skips profiles with explicit `is_active = false`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_send_to_clan.py` (reuse the module's existing imports/fixture):

```python
@pytest.mark.asyncio
async def test_send_to_clan_excludes_deactivated_members(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H1 (review 2026-07-18): a deactivated member must not receive clan push
    content. Only an explicit is_active=false excludes — the LEFT JOIN's NULL
    profile (edge case) still receives, matching the None-is-not-deactivated
    semantics of the auth chokepoint."""
    captured: list[Any] = []

    def _send_each(msgs: list[Any]) -> SimpleNamespace:
        captured.extend(msgs)
        return SimpleNamespace(
            responses=[SimpleNamespace(success=True, exception=None) for _ in msgs]
        )

    monkeypatch.setattr(notif.messaging, "send_each", MagicMock(side_effect=_send_each))
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    clan_id = uuid.uuid4()
    active_id, deact_id = uuid.uuid4(), uuid.uuid4()
    active_token = f"tok-{uuid.uuid4().hex}"
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:i,'C',:sg)"),
            {"i": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        for uid, active in ((active_id, True), (deact_id, False)):
            await s.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name, is_active) "
                    "VALUES (:i, :e, 'U', :act)"
                ),
                {"i": uid, "e": f"u-{uid.hex[:6]}@x.io", "act": active},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(clan_id, user_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:c, :u, 'viewer', true, :u, NOW())"
                ),
                {"c": clan_id, "u": uid},
            )
        await s.execute(
            sa.text(
                "INSERT INTO user_fcm_tokens (user_id, token, device_platform) "
                "VALUES (:u, :t, 'android')"
            ),
            {"u": active_id, "t": active_token},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_fcm_tokens (user_id, token, device_platform) "
                "VALUES (:u, :t, 'android')"
            ),
            {"u": deact_id, "t": f"tok-{uuid.uuid4().hex}"},
        )
        await s.commit()

    async with maker() as db:
        sent, failed = await notif.send_to_clan(
            clan_id=clan_id,
            title_key="notification.birthday.title",
            body_key="notification.birthday.body",
            db=db,
            name="An",
        )
    assert (sent, failed) == (1, 0)
    assert len(captured) == 1 and captured[0].token == active_token
```

(`Any` may need adding to this module's imports: `from typing import Any`.)

- [ ] **Step 2: Run — verify FAIL**

Run: `cd backend && uv run pytest tests/integration/test_send_to_clan.py -v`
Expected: new test FAILS with `(sent, failed) == (2, 0)`; existing test PASSES.

- [ ] **Step 3: Add the filter to the SQL**

In `backend/app/services/notification.py::send_to_clan`, add one predicate to the WHERE clause of the member SELECT:

```sql
              AND (up.is_active IS DISTINCT FROM false)
```

(placed after `AND ucr.is_approved = true`). `IS DISTINCT FROM false` — not `= true` — keeps the None-is-not-deactivated semantics for a NULL profile from the LEFT JOIN.

- [ ] **Step 4: Run — verify PASS**

Run: `cd backend && uv run pytest tests/integration/test_send_to_clan.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notification.py backend/tests/integration/test_send_to_clan.py
git commit -m "fix(notifications): exclude deactivated members from clan fan-out"
```

---

### Task 5: Doc sync (grep-verified, per the ADR-024 lesson)

**Files:**
- Modify: `docs/architecture/auth-flow.md`
- Modify: `docs/contracts/error-codes.md`
- Modify: `docs/contracts/rest-auth-api.md`
- Possibly: any other file surfaced by the grep in Step 1.

- [ ] **Step 1: Enumerate every doc that describes where deactivation is enforced**

Run: `grep -rn "is_active\|deactivat" docs/contracts docs/architecture --include='*.md' | grep -vi "clan_suspended\|clans.is_active\|review-2026-07-18"`
Every hit that says the check happens "on profile load", "on clan-scoped requests", or in `ensure_user_profile`/`get_current_clan_id` must be updated in the steps below. Known hits: `docs/architecture/auth-flow.md:20,71`, `docs/contracts/error-codes.md:65`. Check also `frontend-integration-guide.md`, `rest-me-api.md`, `multi-tenancy.md`, `rbac.md`, `api-design.md` from the grep output.

- [ ] **Step 2: Update `auth-flow.md`**

Rewrite the deactivation-gate bullet (line ~20) to state: enforced in `get_current_user` — the single chokepoint on **every authenticated request** (H1 fix, 2026-07-18); also enforced at `POST /auth/login` (no tokens/profile returned); `POST /auth/refresh` is intentionally ungated (DB-free `AuthSessionService`; refreshed tokens are inert because every API call re-checks); a deactivated user consequently cannot call `POST /auth/logout` (accepted consequence).

- [ ] **Step 3: Update `error-codes.md`**

Line ~65: change the `account_deactivated` trigger column from "checked on profile load and on every clan-scoped request" to "checked on every authenticated request (`get_current_user` chokepoint) and at login".

- [ ] **Step 4: Update `rest-auth-api.md`**

In the login operation's behavior notes add: a deactivated account (`is_active = false`) receives 403 `account_deactivated` — no tokens, no profile. In the refresh operation's notes add: refresh itself is not gated on `is_active`; the tokens it returns are unusable against the API (every authenticated request is gated).

- [ ] **Step 5: Re-run the Step 1 grep — confirm no stale locations remain, then commit**

```bash
git add docs/
git commit -m "docs(auth): deactivation is a chokepoint invariant — sync contracts + auth-flow (H1)"
```

---

### Task 6: Full gate + branch verification

- [ ] **Step 1: Full quality gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`
Expected: all five green.

- [ ] **Step 2: Verify the sabotage property held**

Confirm from Task 1's history that Step 2 (RED) showed the four bypass tests failing before the gate existed — that is the negative control for this invariant. No code change in this step.
