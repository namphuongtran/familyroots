# Auth Email Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require a verified email before an account can authenticate — create users unconfirmed, send a Supabase confirmation email (Approach A: admin create + anon `resend`), reject unverified logins with a clean 403, and expose a non-enumerating resend endpoint.

**Architecture:** Two concerns, one PR. Task 1 = enforcement (create unconfirmed + classify Supabase "email_not_confirmed" → a new domain exception → 403 handler). Task 2 = sending (port/adapter `send_verification_email` via `resend(type=signup)`, wired into register best-effort + a `POST /auth/resend-verification` endpoint). Mirrors the existing password-reset integration throughout.

**Tech Stack:** FastAPI, Supabase Auth SDK (`supabase_auth`), SQLAlchemy async, pytest-asyncio (stub `IdentityProvider` via `get_identity_provider` DI seam + real RS256 JWT; no live Supabase).

## Global Constraints

- **Approach A**: keep `admin.create_user` (clean `IdentityUserExistsError` detection + `delete_user` compensation) — change only `email_confirm=True` → `False`, and send the email via anon `resend`.
- **Detect the login rejection by error CODE** `email_not_confirmed` (a real `supabase_auth` `ErrorCode`), not message text.
- **`IdentityEmailNotVerifiedError` is a sibling of `IdentityAuthError`** (both extend `IdentityError`) so `login`'s `except IdentityAuthError` does NOT catch it — it propagates to a global 403 handler, exactly like `IdentityUnavailableError` → 503.
- **Register sends the verify email best-effort** (swallow + log): a transient SMTP failure must not fail an otherwise-successful registration. Send only AFTER clan assignment succeeds (never for a compensated/rolled-back account).
- **Resend endpoint is non-enumerating**: always 200 + fixed message, swallow provider errors (byte-for-byte the `/forgot-password` pattern).
- **No schema/migration change.** `RegisterResponse` shape unchanged. Existing routes' response shapes unchanged (new resend route uses `{"data": ...}`).
- **i18n**: every new user-facing string in all 4 locales (`en`, `fr`, `vi`, `zh`); flat keys (e.g. `"error.email_not_verified"`).
- **Quality gate (full, every task)** from `backend/`: `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` (use `uv run mypy`, NOT bare `uvx mypy`). All pass before commit.

---

## File Structure

| File | Change |
|---|---|
| `app/domain/auth/identity_provider.py` | Add `IdentityEmailNotVerifiedError`; add `send_verification_email` to the `IdentityProvider` Protocol |
| `app/infrastructure/supabase_identity_provider.py` | `create_user` → `email_confirm=False`; `_classify` maps `email_not_confirmed`; add `send_verification_email` (anon `resend`) |
| `app/core/exceptions.py` | Add `identity_email_not_verified_handler` (403) |
| `app/main.py` | Register the new handler |
| `app/core/config.py` | Add `EMAIL_VERIFY_REDIRECT_URL` |
| `app/application/auth/handlers.py` | Register wires best-effort send; `AuthSessionService.send_verification_email` |
| `app/api/v1/auth.py` | `POST /resend-verification` |
| `app/schemas/auth.py` | `ResendVerificationRequest` |
| `app/i18n/{en,fr,vi,zh}.json` | `error.email_not_verified`, `auth.verification_email_sent` |
| `tests/unit/infrastructure/test_identity_error_classification.py` | Extend pinned table |
| `tests/unit/infrastructure/test_supabase_identity_provider*.py` (or new) | Adapter: `email_confirm=False`, `resend` args |
| `tests/integration/test_auth_http_flow.py` | Stub gains `send_verification_email`; login-unverified → 403; register sends after assignment |
| `tests/unit/api/test_resend_verification.py` (new) | Resend endpoint non-enumerating |

---

## Task 1: Enforce — unverified accounts cannot log in

**Files:**
- Modify: `backend/app/domain/auth/identity_provider.py`
- Modify: `backend/app/infrastructure/supabase_identity_provider.py`
- Modify: `backend/app/core/exceptions.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/i18n/{en,fr,vi,zh}.json`
- Test: `backend/tests/unit/infrastructure/test_identity_error_classification.py`, `backend/tests/integration/test_auth_http_flow.py`

**Interfaces:**
- Produces: `IdentityEmailNotVerifiedError(IdentityError)`; `_classify(AuthApiError code="email_not_confirmed") -> IdentityEmailNotVerifiedError`; a registered handler returning **403** `{"error": {"code": "email_not_verified", ...}}`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/unit/infrastructure/test_identity_error_classification.py`, add cases (follow the file's existing pinned-table style — read it first):

```python
def test_email_not_confirmed_maps_to_email_not_verified() -> None:
    from supabase_auth.errors import AuthApiError

    from app.domain.auth.identity_provider import IdentityEmailNotVerifiedError
    from app.infrastructure.supabase_identity_provider import _classify

    exc = AuthApiError("Email not confirmed", 400, "email_not_confirmed")
    assert isinstance(_classify(exc), IdentityEmailNotVerifiedError)


def test_generic_400_still_maps_to_auth_error() -> None:
    from supabase_auth.errors import AuthApiError

    from app.domain.auth.identity_provider import IdentityAuthError
    from app.infrastructure.supabase_identity_provider import _classify

    exc = AuthApiError("Invalid login credentials", 400, "invalid_credentials")
    assert isinstance(_classify(exc), IdentityAuthError)
```

In `backend/tests/integration/test_auth_http_flow.py`, add a login-unverified test. Use the existing harness (`client` fixture built on `create_app` + JWKS-injected stub). Add a provider variant whose `sign_in` raises the not-verified error, override `get_identity_provider`, and assert 403 + envelope code. Concretely (adapt names to the file's fixtures):

```python
def test_login_unverified_email_returns_403(client_factory, rsa_keys) -> None:
    """An unconfirmed email must surface as 403 email_not_verified, not 401."""
    from app.domain.auth.identity_provider import IdentityEmailNotVerifiedError
    from app.infrastructure.dependencies import get_identity_provider

    class _Unverified(StubIdentityProvider):
        async def sign_in(self, *, email: str, password: str):
            raise IdentityEmailNotVerifiedError("Email not confirmed")

    app, _ = client_factory()  # however the file builds app+client; reuse its helper
    app.dependency_overrides[get_identity_provider] = lambda: _Unverified(rsa_keys["private_pem"])
    with TestClient(app) as c:
        resp = c.post("/api/v1/auth/login", json={"email": "a@ex.com", "password": "secret123"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "email_not_verified"
```

(If `test_auth_http_flow.py` builds the app inline rather than via a factory fixture, mirror that file's exact construction — the key points are: override `get_identity_provider` with a `sign_in` that raises `IdentityEmailNotVerifiedError`, POST `/api/v1/auth/login`, assert 403 + `error.code == "email_not_verified"`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/infrastructure/test_identity_error_classification.py -k email_not -xvs && uv run pytest tests/integration/test_auth_http_flow.py -k unverified -xvs`
Expected: FAIL — `IdentityEmailNotVerifiedError` doesn't exist; login returns 401 (no handler) not 403.

- [ ] **Step 3: Add the domain exception**

In `backend/app/domain/auth/identity_provider.py`, after `IdentityAuthError` (line 41-42), add:

```python
class IdentityEmailNotVerifiedError(IdentityError):
    """The account exists but its email has not been confirmed yet.

    A distinct sibling of IdentityAuthError (NOT a subclass) so a caller catching
    IdentityAuthError does not swallow it — it propagates to a dedicated 403 handler,
    the same way IdentityUnavailableError propagates to its 503 handler."""
```

- [ ] **Step 4: Classify it + create unconfirmed**

In `backend/app/infrastructure/supabase_identity_provider.py`:

Import the new exception (add to the existing `from app.domain.auth.identity_provider import (...)` block): `IdentityEmailNotVerifiedError`.

In `_classify`, at the TOP of the `if isinstance(exc, AuthApiError):` branch (before the `"api key"` check), add:

```python
        if isinstance(exc, AuthApiError):
            if exc.code == "email_not_confirmed":
                # Account exists but unverified — a 403 "verify your email", NOT a 401.
                return IdentityEmailNotVerifiedError(str(exc))
            if "api key" in str(exc).lower():
```

Change `create_user` (line 67-69) to create the user **unconfirmed**:

```python
            resp = sb.auth.admin.create_user(
                {"email": email, "password": password, "email_confirm": False}
            )
```

- [ ] **Step 5: Add the 403 handler + register it**

In `backend/app/core/exceptions.py`, after `identity_unavailable_handler`, add (mirror it, status 403):

```python
async def identity_email_not_verified_handler(request: Request, exc: Exception) -> JSONResponse:
    """Surface an unverified-email login as 403 in one place (never 401)."""
    from app.services.translator import t

    code = "email_not_verified"
    return JSONResponse(
        status_code=403,
        content={"error": {"code": code, "message": t(f"error.{code}"), "detail": {}}},
    )
```

In `backend/app/main.py`: add `IdentityEmailNotVerifiedError` to the existing
`from app.domain.auth.identity_provider import IdentityUnavailableError` import, add
`identity_email_not_verified_handler` to the handlers import from `app.core.exceptions`, and register it beside the unavailable handler (line 128):

```python
    application.add_exception_handler(IdentityUnavailableError, identity_unavailable_handler)
    application.add_exception_handler(
        IdentityEmailNotVerifiedError, identity_email_not_verified_handler
    )
```

- [ ] **Step 6: Add i18n key (all 4 locales)**

Add `"error.email_not_verified"` next to `"error.auth_provider_unavailable"` in each of `app/i18n/{vi,en,fr,zh}.json`:

- vi: `"error.email_not_verified": "Vui lòng xác minh email của bạn trước khi đăng nhập."`
- en: `"error.email_not_verified": "Please verify your email address before signing in."`
- fr: `"error.email_not_verified": "Veuillez vérifier votre adresse e-mail avant de vous connecter."`
- zh: `"error.email_not_verified": "请先验证您的邮箱后再登录。"`

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/infrastructure/test_identity_error_classification.py tests/integration/test_auth_http_flow.py -v`
Expected: PASS (email_not_confirmed→exception; generic 400 still →IdentityAuthError; login-unverified→403; existing flow tests unchanged).

- [ ] **Step 8: Run the full gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add app/domain/auth/identity_provider.py app/infrastructure/supabase_identity_provider.py app/core/exceptions.py app/main.py app/i18n/en.json app/i18n/fr.json app/i18n/vi.json app/i18n/zh.json tests/unit/infrastructure/test_identity_error_classification.py tests/integration/test_auth_http_flow.py
git commit -m "feat(backend): reject unverified-email login with 403; create users unconfirmed (email-verification)"
```

---

## Task 2: Send the verification email + resend endpoint

**Files:**
- Modify: `backend/app/domain/auth/identity_provider.py` (port)
- Modify: `backend/app/infrastructure/supabase_identity_provider.py` (adapter)
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/application/auth/handlers.py`
- Modify: `backend/app/api/v1/auth.py`
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/i18n/{en,fr,vi,zh}.json`
- Modify: `backend/tests/integration/test_auth_http_flow.py` (stub gains method + register-sends test)
- Test: `backend/tests/unit/api/test_resend_verification.py` (new)

**Interfaces:**
- Consumes: `IdentityProvider` (Task 1), `AuthSessionService`, `AuthCommandHandler.register`.
- Produces: `IdentityProvider.send_verification_email(*, email: str) -> None`; `AuthSessionService.send_verification_email(*, email: str)`; `POST /auth/resend-verification` → `{"data": {"message": ...}}`; `ResendVerificationRequest{email: EmailStr}`; `Settings.EMAIL_VERIFY_REDIRECT_URL`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/api/test_resend_verification.py`:

```python
"""POST /auth/resend-verification is non-enumerating: always 200, swallows provider errors."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.auth import router as auth_router
from app.application.auth.handlers import AuthSessionService
from app.infrastructure.dependencies import get_auth_session_service


class _Svc:
    def __init__(self, *, boom: bool) -> None:
        self.boom = boom
        self.called_with: str | None = None

    async def send_verification_email(self, *, email: str) -> None:
        self.called_with = email
        if self.boom:
            raise RuntimeError("provider down")


def _client(svc: _Svc) -> TestClient:
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1/auth")
    app.dependency_overrides[get_auth_session_service] = lambda: svc
    return TestClient(app)


def test_resend_verification_ok() -> None:
    svc = _Svc(boom=False)
    resp = _client(svc).post("/api/v1/auth/resend-verification", json={"email": "a@ex.com"})
    assert resp.status_code == 200
    assert "data" in resp.json() and "message" in resp.json()["data"]
    assert svc.called_with == "a@ex.com"


def test_resend_verification_swallows_provider_error() -> None:
    """Provider failure must NOT leak (still 200, same message) — non-enumerating."""
    resp = _client(_Svc(boom=True)).post(
        "/api/v1/auth/resend-verification", json={"email": "x@ex.com"}
    )
    assert resp.status_code == 200
```

In `backend/tests/integration/test_auth_http_flow.py`: (a) add `send_verification_email` to `StubIdentityProvider`, (b) add a test that a successful register triggers it. Add to the stub class (after `update_user`):

```python
    async def send_verification_email(self, *, email: str) -> None:
        self.verification_emails.append(email)
```

and initialize `self.verification_emails: list[str] = []` in the stub's `__init__`. Then a test (reuse the file's register helper/harness):

```python
def test_register_sends_verification_email(client, stub_identity) -> None:
    """A successful registration triggers exactly one verification email for that address."""
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@ex.com",
            "password": "secret123",
            "full_name": "New User",
            "clan_action": "create",
            "clan_name": "Nguyen",
            "clan_slug": "nguyen-test",
        },
    )
    assert resp.status_code == 201
    assert stub_identity.verification_emails == ["newuser@ex.com"]
```

(Match the file's actual `client`/`stub_identity` fixture wiring — the point: after a 201 register, the stub recorded the verification email for the registrant.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/api/test_resend_verification.py tests/integration/test_auth_http_flow.py -k "resend or verification" -xvs`
Expected: FAIL — `/resend-verification` route 404s; `AuthSessionService`/stub lack `send_verification_email`; register doesn't record an email.

- [ ] **Step 3: Add the port method + adapter**

In `backend/app/domain/auth/identity_provider.py`, add to the `IdentityProvider` Protocol (after `send_password_reset`):

```python
    async def send_verification_email(self, *, email: str) -> None:
        """Best-effort: (re)send the signup email-verification link via the provider.

        Confirmation completes via the provider's hosted flow + the configured
        redirect target — this only triggers the email."""
        ...
```

In `backend/app/infrastructure/supabase_identity_provider.py`, add the adapter method (mirror `send_password_reset`):

```python
    async def send_verification_email(self, *, email: str) -> None:
        # Anon client; off-loaded (blocking SDK). `resend` type=signup re-sends the
        # confirmation email for an unconfirmed account. redirect only when configured.
        options: dict[str, Any] = {}
        if settings.EMAIL_VERIFY_REDIRECT_URL:
            options["email_redirect_to"] = settings.EMAIL_VERIFY_REDIRECT_URL
        await asyncio.to_thread(
            get_anon_client().auth.resend,
            {"type": "signup", "email": email, "options": options},  # type: ignore[arg-type]
        )
```

- [ ] **Step 4: Add config**

In `backend/app/core/config.py`, next to `PASSWORD_RESET_REDIRECT_URL` (line 73):

```python
    EMAIL_VERIFY_REDIRECT_URL: str = ""
```

- [ ] **Step 5: Wire register + AuthSessionService**

In `backend/app/application/auth/handlers.py`:

Add to `AuthSessionService` (after `send_password_reset`):

```python
    async def send_verification_email(self, *, email: str) -> None:
        """Trigger a provider email-verification (best-effort)."""
        await self._identity.send_verification_email(email=email)
```

In `AuthCommandHandler.register`, replace the `try/except` around `_assign_clan_membership` (lines 224-241) so the verify email is sent after success only:

```python
        user_id = uuid.UUID(user_id_str)
        try:
            response = await self._assign_clan_membership(
                user_id=user_id,
                email=email,
                full_name=full_name,
                clan_action=clan_action,
                clan_id=clan_id,
                clan_name=clan_name,
                clan_slug=clan_slug,
            )
        except Exception:
            # Compensate: the auth user exists but DB membership failed — delete the
            # orphan so the email can be reused. No verification email was sent.
            with suppress(Exception):
                await self._identity.delete_user(str(user_id))
            raise

        # Registration succeeded — send the email-verification link best-effort. A
        # transient SMTP failure must not fail the registration; the user can
        # re-trigger via POST /auth/resend-verification.
        with suppress(Exception):
            await self._identity.send_verification_email(email=email)
        return response
```

- [ ] **Step 6: Add the schema + route**

In `backend/app/schemas/auth.py`, next to `ForgotPasswordRequest`:

```python
class ResendVerificationRequest(BaseModel):
    email: EmailStr
```

In `backend/app/api/v1/auth.py`, add `ResendVerificationRequest` to the `from app.schemas.auth import (...)` block, and add the route (after `forgot_password`):

```python
@router.post("/resend-verification")
async def resend_verification(
    body: ResendVerificationRequest,
    svc: AuthSessionService = Depends(get_auth_session_service),
) -> dict[str, Any]:
    """Resend the email-verification link. ALWAYS returns 200 with the same message
    regardless of whether the email exists or the provider is reachable — never leak
    account existence or provider state."""
    try:
        await svc.send_verification_email(email=body.email)
    except Exception as e:
        logger.warning("resend-verification: provider call failed (swallowed): %s", e)
    return {"data": {"message": t("auth.verification_email_sent")}}
```

- [ ] **Step 7: Add i18n key (all 4 locales)**

Add `"auth.verification_email_sent"` next to `"auth.password_reset_sent"` in each of `app/i18n/{vi,en,fr,zh}.json`:

- vi: `"auth.verification_email_sent": "Nếu email này chưa xác minh, chúng tôi đã gửi lại liên kết xác minh."`
- en: `"auth.verification_email_sent": "If this email is unverified, we've sent a verification link."`
- fr: `"auth.verification_email_sent": "Si cet e-mail n'est pas vérifié, nous avons envoyé un lien de vérification."`
- zh: `"auth.verification_email_sent": "如果该邮箱尚未验证，我们已发送验证链接。"`

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/api/test_resend_verification.py tests/integration/test_auth_http_flow.py -v`
Expected: PASS (resend 200 + swallow; register records the verification email).

- [ ] **Step 9: Run the full gate**

Run: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`
Expected: all green.

- [ ] **Step 10: Commit**

```bash
git add app/domain/auth/identity_provider.py app/infrastructure/supabase_identity_provider.py app/core/config.py app/application/auth/handlers.py app/api/v1/auth.py app/schemas/auth.py app/i18n/en.json app/i18n/fr.json app/i18n/vi.json app/i18n/zh.json tests/unit/api/test_resend_verification.py tests/integration/test_auth_http_flow.py
git commit -m "feat(backend): send email-verification on register + POST /auth/resend-verification (email-verification)"
```

---

## Self-Review

**1. Spec coverage:**
- Create unconfirmed (`email_confirm=False`) → Task 1 Step 4. ✅
- Classify `email_not_confirmed` → `IdentityEmailNotVerifiedError` (by code) → Task 1 Steps 3-4 + classification test. ✅
- 403 handler + i18n `error.email_not_verified` → Task 1 Steps 5-6; login→403 test. ✅
- `send_verification_email` port + adapter (anon `resend`, optional redirect) → Task 2 Steps 3-4. ✅
- Register best-effort send after assignment, not on compensation → Task 2 Step 5; register-sends test (+ compensation implicitly: send is after the try/except, so a failed assignment re-raises before the send). ✅
- `POST /auth/resend-verification` non-enumerating → Task 2 Step 6 + resend tests (ok + swallow). ✅
- Config `EMAIL_VERIFY_REDIRECT_URL` → Task 2 Step 4. ✅
- No schema change; RegisterResponse unchanged; existing routes unchanged. ✅

**2. Placeholder scan:** No TBD/TODO. Two tests (login-403, register-sends) say "match the file's actual fixture wiring" — this is a real constraint (the harness construction lives in that file), with the exact assertions specified; not a placeholder for logic. ✅

**3. Type consistency:** `send_verification_email(*, email: str) -> None` identical across port, adapter, `AuthSessionService`, stub, and the resend `_Svc` double. `IdentityEmailNotVerifiedError` defined in Task 1, imported by the adapter (`_classify`), `main.py` (handler registration), and the tests. `ResendVerificationRequest{email: EmailStr}` matches the route param + the mirrored `ForgotPasswordRequest`. Register returns the `_assign_clan_membership` result unchanged (`RegisterResponse`). ✅
```
