# SP-2C: Auth Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the Supabase-backed auth path: validate the JWT issuer, normalize the inline `SupabaseAuthService()` constructions onto the composition root, remove the dead `SUPABASE_JWT_SECRET` config, implement a real (refresh-token-revoking) logout, and compensate for the orphaned Supabase auth user when a registration's DB transaction aborts.

**Architecture:** Auth is Supabase JWT validated against the project's JWKS (`app/core/security.py`). Routes delegate to `AuthCommandHandler` (DB-bound) and `SupabaseAuthService` (DB-free Supabase calls). We add issuer validation to the JWKS decode; provide `SupabaseAuthService` via a DI provider so routes stop constructing it inline; delete the unused secret; add a token-revoking `logout`; and wrap `register`'s post-create DB work in a compensating delete of the Supabase user on failure.

**Tech Stack:** Python 3.14, FastAPI, python-jose, supabase-py, SQLAlchemy async, pytest, `uv`.

## Global Constraints

- Python `>=3.14`; line length 100; ruff selectors per `pyproject.toml`.
- Domain layer framework-agnostic; application imports domain + ports only.
- JWT validation must verify signature (RS256/JWKS), `exp`, audience (`authenticated`), AND issuer (`{SUPABASE_URL}/auth/v1`).
- Routes resolve handlers/services via `app/infrastructure/dependencies.py` providers (`Depends(...)`), not by constructing them inline.
- `SUPABASE_JWT_SECRET` is dead config (defined in `config.py:29`, referenced nowhere in `app/`) — remove it.
- A failed registration must not leave an orphaned Supabase auth user (which would block re-registration with `auth.email_already_exists`).
- For supabase-py calls whose exact method/signature you are unsure of, INTROSPECT the installed package (e.g. `uv run python -c "import supabase, inspect; ..."`) and confirm before using — do not guess.
- Run tests from `backend/`: `uv run pytest <path> -v`. Lint: `uvx ruff check <path>`.

---

## Files

- Modify: `backend/app/core/security.py` — issuer validation in `verify_supabase_token`.
- Test: `backend/tests/unit/test_token_verification.py` (new) — issuer accept/reject.
- Modify: `backend/app/core/config.py:29` + `backend/.env.example` — remove `SUPABASE_JWT_SECRET`.
- Modify: `backend/app/infrastructure/dependencies.py` — add `get_supabase_auth_service`.
- Modify: `backend/app/api/v1/auth.py` — `refresh_token`, `update_me`, `logout` use the DI provider; `logout` revokes the session.
- Modify: `backend/app/application/auth/handlers.py` — `SupabaseAuthService.logout`; `AuthCommandHandler.register` compensation.
- Test: `backend/tests/unit/application/test_auth_register_compensation.py` (new).
- Test: `backend/tests/unit/application/test_supabase_auth_service.py` (new) — logout revocation call.

---

## Task 1: Validate the JWT issuer

**Files:**
- Modify: `backend/app/core/security.py:60-72`
- Create: `backend/tests/unit/test_token_verification.py`

**Interfaces:**
- Produces: `verify_supabase_token` rejects (HTTP 401) a token whose `iss` is not `{settings.SUPABASE_URL}/auth/v1`, in addition to the existing signature/exp/audience checks.

- [ ] **Step 1: Write the failing test (real RS256 token + mocked JWKS)**

Create `backend/tests/unit/test_token_verification.py`. It generates an RSA keypair, builds a JWK, mocks `get_supabase_jwks` to return it, and verifies issuer accept/reject:

```python
"""verify_supabase_token must reject tokens with a wrong issuer."""

import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk, jwt
from jose.constants import ALGORITHMS

from app.core import security
from app.core.config import settings


def _make_keypair_and_jwk():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    public_jwk = jwk.construct(pub_pem, ALGORITHMS.RS256).to_dict()
    public_jwk["kid"] = "test-key"
    public_jwk = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in public_jwk.items()}
    return priv_pem, {"keys": [public_jwk]}


@pytest.fixture()
def signing(monkeypatch):
    priv_pem, jwks = _make_keypair_and_jwk()
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://proj.supabase.co")

    async def _fake_jwks():
        return jwks

    monkeypatch.setattr(security, "get_supabase_jwks", _fake_jwks)
    return priv_pem


def _token(priv_pem, iss):
    return jwt.encode(
        {"sub": "u1", "aud": "authenticated", "iss": iss, "exp": 9999999999},
        priv_pem,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


@pytest.mark.asyncio
async def test_correct_issuer_accepted(signing):
    token = _token(signing, "https://proj.supabase.co/auth/v1")
    payload = await security.verify_supabase_token(token)
    assert payload["sub"] == "u1"


@pytest.mark.asyncio
async def test_wrong_issuer_rejected(signing):
    from fastapi import HTTPException

    token = _token(signing, "https://evil.example.com/auth/v1")
    with pytest.raises(HTTPException) as exc:
        await security.verify_supabase_token(token)
    assert exc.value.status_code == 401
```

- [ ] **Step 2: Run — confirm `test_wrong_issuer_rejected` fails**

Run: `cd backend && uv run pytest tests/unit/test_token_verification.py -v`
Expected: `test_correct_issuer_accepted` passes but `test_wrong_issuer_rejected` FAILS (no issuer check yet — the wrong-issuer token currently decodes fine).

- [ ] **Step 3: Add issuer validation**

In `security.py`, update the `jwt.decode` call (lines 64-69) to pass `issuer`:

```python
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience="authenticated",
            issuer=f"{settings.SUPABASE_URL}/auth/v1",
        )
```

- [ ] **Step 4: Run — confirm both pass**

Run: `cd backend && uv run pytest tests/unit/test_token_verification.py -v`
Expected: both PASS (wrong issuer → `JWTError` → caught → HTTP 401).

- [ ] **Step 5: Lint + commit**

```bash
cd backend && uvx ruff check app/core/security.py tests/unit/test_token_verification.py
git add -A && git commit -m "fix(auth): validate JWT issuer against Supabase project URL"
```

---

## Task 2: Provide SupabaseAuthService via DI; stop inline construction

**Files:**
- Modify: `backend/app/infrastructure/dependencies.py`
- Modify: `backend/app/api/v1/auth.py:83-116`

**Interfaces:**
- Produces: `get_supabase_auth_service() -> SupabaseAuthService` in `dependencies.py`. The `refresh_token` and `update_me` routes receive it via `Depends(get_supabase_auth_service)` instead of `SupabaseAuthService()` inline.

- [ ] **Step 1: Add the DI provider**

In `dependencies.py`, add (near the other auth providers around line 144):

```python
def get_supabase_auth_service() -> "SupabaseAuthService":
    from app.application.auth.handlers import SupabaseAuthService

    return SupabaseAuthService()
```

(If the file imports handler classes under `TYPE_CHECKING` at line 15, add `SupabaseAuthService` to that import for the annotation; otherwise the string annotation + local import is sufficient.)

- [ ] **Step 2: Use the provider in the routes**

In `auth.py`, update `refresh_token` (lines 83-87) and `update_me` (lines 104-116) to inject the service. Add `get_supabase_auth_service` to the `from app.infrastructure.dependencies import (...)` block, and:

```python
@router.post("/refresh")
async def refresh_token(
    body: RefreshRequest,
    svc: SupabaseAuthService = Depends(get_supabase_auth_service),
) -> dict[str, Any]:
    """Exchange a refresh token for a new access token."""
    return await svc.refresh_token(refresh_token=body.refresh_token)
```

```python
@router.patch("/me")
async def update_me(
    body: UserUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    svc: SupabaseAuthService = Depends(get_supabase_auth_service),
) -> dict[str, Any]:
    """Update the authenticated user's profile."""
    await svc.update_profile(
        user_sub=current_user["sub"],
        full_name=body.full_name,
        preferred_locale=body.preferred_locale,
    )
    return {"data": {"message": t("auth.profile_updated")}}
```

- [ ] **Step 3: Verify no inline construction remains in routes**

Run: `cd backend && grep -n "SupabaseAuthService()" app/api/v1/auth.py`
Expected: no output (the only remaining reference to `SupabaseAuthService` in auth.py is the type annotation import).

- [ ] **Step 4: Lint + import-sanity + commit**

```bash
cd backend && uvx ruff check app/infrastructure/dependencies.py app/api/v1/auth.py
uv run python -c "import app.api.v1.auth, app.infrastructure.dependencies"
git add -A && git commit -m "refactor(auth): inject SupabaseAuthService via composition root"
```

---

## Task 3: Remove the dead SUPABASE_JWT_SECRET config

**Files:**
- Modify: `backend/app/core/config.py:29`
- Modify: `backend/.env.example`

**Interfaces:**
- Produces: `SUPABASE_JWT_SECRET` no longer exists in `Settings` or `.env.example`. (Confirmed unused: grep over `app/` finds it only at its definition.)

- [ ] **Step 1: Confirm it is unused, then remove**

Run: `cd backend && grep -rn "SUPABASE_JWT_SECRET" app/`
Expected: only `app/core/config.py:29`. Delete that line from `config.py`. Then remove the `SUPABASE_JWT_SECRET=...` line from `backend/.env.example`.

- [ ] **Step 2: Verify nothing references it and config still loads**

Run: `cd backend && grep -rn "SUPABASE_JWT_SECRET" app/ .env.example; uv run python -c "from app.core.config import settings; print('ok')"`
Expected: no grep matches; prints `ok`.

- [ ] **Step 3: Lint + commit**

```bash
cd backend && uvx ruff check app/core/config.py
git add -A && git commit -m "chore(config): remove unused SUPABASE_JWT_SECRET"
```

---

## Task 4: Real logout — revoke the session's refresh tokens

**Files:**
- Modify: `backend/app/application/auth/handlers.py` (`SupabaseAuthService`)
- Modify: `backend/app/api/v1/auth.py:77-80`
- Create: `backend/tests/unit/application/test_supabase_auth_service.py`

**Interfaces:**
- Produces: `SupabaseAuthService.logout(access_token: str) -> None` revokes the user's Supabase session (refresh tokens) so the session cannot be renewed. The `/logout` route passes the caller's bearer token and returns the localized message after revocation.

- [ ] **Step 1: Confirm the supabase-py revocation API on the installed version**

Run: `cd backend && uv run python -c "from supabase import create_client; import inspect; from supabase_auth._sync.gotrue_admin_api import SyncGoTrueAdminAPI as A; print([m for m in dir(A) if 'sign' in m.lower() or 'logout' in m.lower()])"`
(If that import path differs, introspect `supabase_auth` to find the admin API class.) Note the exact method (expected: `sign_out(jwt, scope)` on the admin API, or `auth.admin.sign_out`). Record what you find in your report and use that exact call below. If NO server-side revocation method exists on the installed version, STOP and report BLOCKED with the introspection output — do not fake it.

- [ ] **Step 2: Write the failing test (mock the Supabase admin client)**

Create `backend/tests/unit/application/test_supabase_auth_service.py`:

```python
"""SupabaseAuthService.logout must revoke the user's session via Supabase."""

from unittest.mock import MagicMock

import pytest

from app.application.auth import handlers


@pytest.mark.asyncio
async def test_logout_revokes_session(monkeypatch):
    admin = MagicMock()
    monkeypatch.setattr(handlers, "_supabase_admin", lambda: admin)

    svc = handlers.SupabaseAuthService()
    await svc.logout(access_token="the-access-token")

    # The service must have asked Supabase to sign the session out.
    assert admin.auth.admin.sign_out.called
```

(Adjust `admin.auth.admin.sign_out` to the exact call path you confirmed in Step 1.)

- [ ] **Step 3: Run — confirm it fails**

Run: `cd backend && uv run pytest tests/unit/application/test_supabase_auth_service.py -v`
Expected: FAIL — `SupabaseAuthService` has no `logout` method (AttributeError).

- [ ] **Step 4: Implement `logout`**

Add to `SupabaseAuthService` in `handlers.py` (use the exact method/signature confirmed in Step 1; the shape below assumes `admin.sign_out(jwt, scope)`):

```python
    async def logout(self, *, access_token: str) -> None:
        """Revoke the user's Supabase session (refresh tokens).

        The stateless access token remains valid until its short expiry; this
        prevents the session from being renewed.
        """
        sb = _supabase_admin()
        try:
            sb.auth.admin.sign_out(access_token, "global")
        except Exception:  # noqa: BLE001 — logout is best-effort; never 500 on it
            return
```

- [ ] **Step 5: Wire the route to pass the bearer token**

In `auth.py`, update `logout` to extract the bearer token and call the service. Add imports `from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer` is unnecessary — reuse `app.core.security.security` (the existing `HTTPBearer` instance) or add a small dependency. Concretely:

```python
from app.core.security import get_current_user, security  # security = HTTPBearer()
from fastapi.security import HTTPAuthorizationCredentials
from app.application.auth.handlers import SupabaseAuthService  # already imported
```

```python
@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: dict[str, Any] = Depends(get_current_user),
    svc: SupabaseAuthService = Depends(get_supabase_auth_service),
) -> dict[str, Any]:
    """Invalidate the current session (revoke refresh tokens)."""
    await svc.logout(access_token=credentials.credentials)
    return {"message": t("auth.logged_out")}
```

- [ ] **Step 6: Run the test + import sanity**

Run: `cd backend && uv run pytest tests/unit/application/test_supabase_auth_service.py -v && uv run python -c "import app.api.v1.auth"`
Expected: PASS; import OK.

- [ ] **Step 7: Lint + commit**

```bash
cd backend && uvx ruff check app/application/auth/handlers.py app/api/v1/auth.py tests/unit/application/test_supabase_auth_service.py
git add -A && git commit -m "feat(auth): real logout revokes Supabase session refresh tokens"
```

---

## Task 5: Compensate orphaned Supabase user on registration DB failure

**Files:**
- Modify: `backend/app/application/auth/handlers.py` (`AuthCommandHandler.register`)
- Create: `backend/tests/unit/application/test_auth_register_compensation.py`

**Interfaces:**
- Consumes: `_supabase_admin()` (service client). `AuthCommandHandler.register` (creates the Supabase user, then runs `_assign_clan_membership`).
- Produces: if `_assign_clan_membership` raises after the Supabase user was created, `register` deletes the orphaned Supabase auth user (best-effort) and re-raises the original error.

- [ ] **Step 1: Confirm the admin delete API**

Run: `cd backend && uv run python -c "from supabase_auth._sync.gotrue_admin_api import SyncGoTrueAdminAPI as A; print([m for m in dir(A) if 'delete' in m.lower()])"`
Expected: a `delete_user` method. Record the exact signature; use it below. If absent, introspect and adapt.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/unit/application/test_auth_register_compensation.py`:

```python
"""register() must delete the orphaned Supabase user if the DB membership fails."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.application.auth import handlers
from app.application.auth.handlers import AuthCommandHandler


@pytest.mark.asyncio
async def test_register_deletes_supabase_user_on_db_failure(monkeypatch):
    new_id = uuid.uuid4()
    admin = MagicMock()
    admin.auth.admin.create_user.return_value = MagicMock(user=MagicMock(id=str(new_id)))
    monkeypatch.setattr(handlers, "_supabase_admin", lambda: admin)

    handler = AuthCommandHandler(repo=MagicMock(), uow=MagicMock())

    async def _boom(**kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(handler, "_assign_clan_membership", _boom)

    with pytest.raises(RuntimeError, match="db exploded"):
        await handler.register(
            email="x@example.com", password="pw", full_name="X",
            clan_action="create", clan_name="C", clan_slug="c-slug",
        )

    # Compensation: the orphaned auth user was deleted.
    admin.auth.admin.delete_user.assert_called_once_with(str(new_id))
```

(Adjust `delete_user` call path/args to what Step 1 confirmed.)

- [ ] **Step 3: Run — confirm it fails**

Run: `cd backend && uv run pytest tests/unit/application/test_auth_register_compensation.py -v`
Expected: FAIL — no compensation; `delete_user` is never called.

- [ ] **Step 4: Implement the compensation**

In `handlers.py`, wrap the `_assign_clan_membership` call in `register` (currently the final `return await self._assign_clan_membership(...)`). Add `from contextlib import suppress` to the imports. Replace the tail of `register`:

```python
        user_id = uuid.UUID(auth_resp.user.id)
        try:
            return await self._assign_clan_membership(
                user_id=user_id,
                email=email,
                full_name=full_name,
                clan_action=clan_action,
                clan_id=clan_id,
                clan_name=clan_name,
                clan_slug=clan_slug,
            )
        except Exception:
            # Compensate: the Supabase auth user exists but the DB membership
            # failed — delete the orphan so the email can be reused.
            with suppress(Exception):
                _supabase_admin().auth.admin.delete_user(str(user_id))
            raise
```

- [ ] **Step 5: Run — confirm pass + the create/onboard paths still import**

Run: `cd backend && uv run pytest tests/unit/application/test_auth_register_compensation.py tests/integration/test_auth_provisioning.py -v`
Expected: the compensation test PASSES and the provisioning integration tests still PASS (happy path unaffected).

- [ ] **Step 6: Lint + commit**

```bash
cd backend && uvx ruff check app/application/auth/handlers.py tests/unit/application/test_auth_register_compensation.py
git add -A && git commit -m "fix(auth): delete orphaned Supabase user when registration DB write fails"
```

---

## Done criteria (SP-2C)

- A token with a wrong `iss` is rejected (401) — `test_token_verification.py` green.
- `refresh_token` / `update_me` resolve `SupabaseAuthService` via DI; no inline `SupabaseAuthService()` in routes.
- `SUPABASE_JWT_SECRET` removed from config + `.env.example`; config still loads.
- `/logout` revokes the Supabase session (refresh tokens) via the confirmed admin API — `test_supabase_auth_service.py` green.
- A registration whose DB write fails deletes the orphaned Supabase user and re-raises — `test_auth_register_compensation.py` green.
- Full unit + integration suite still passes; `ruff check .` clean.

## Notes for the executor

- Run pytest from `backend/`. Tasks 4 and 5 mock Supabase (no network/real Supabase needed); the integration provisioning test in Task 5 Step 5 needs `docker compose up -d pgdb`.
- For Tasks 4 and 5, CONFIRM the exact supabase-py admin method via introspection (Steps 1) before implementing — do not guess the API. If a method is absent on the installed version, report BLOCKED rather than inventing one.
- After all tasks, run `cd backend && uv run pytest tests/unit tests/integration -q` and `uvx ruff check .` to confirm no regressions repo-wide (a prior sub-project's lesson: per-task runs can miss tests outside the task's files).
