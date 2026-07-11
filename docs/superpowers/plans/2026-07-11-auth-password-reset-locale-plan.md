# Auth: Password Reset + user_profiles.language Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backend password-reset trigger (`POST /auth/forgot-password`) and populate `user_profiles.language` from the JWT so PR-H's per-recipient push locale works.

**Architecture:** Password reset follows the existing IdentityProvider port → Supabase adapter → AuthSessionService → route layering; the endpoint is 200-swallow (never leaks account existence or provider state) and reset *completion* is client-side (Supabase PKCE). Locale is synced in `ensure_user_profile` (the per-request chokepoint that already reads the JWT), not the DB-free `AuthSessionService`.

**Tech Stack:** FastAPI, SQLAlchemy async/psycopg, PostgreSQL, Supabase (gotrue) Python SDK, `asyncio.to_thread`, pytest(-asyncio) against dockerized Postgres.

## Global Constraints

- `forgot-password` ALWAYS returns 200 with the same localized body — for a known email, an unknown email, AND a provider outage (log, don't surface). Non-enumerating by construction.
- Reset completion is client-side (Supabase `verify_otp(recovery)` + `update_user(password)`); the backend gets NO `reset-password` endpoint.
- Email verification is OUT OF SCOPE (`email_confirm: True` stays).
- Locale sync lives in `ensure_user_profile`, NOT `update_profile` (keep `AuthSessionService` DB-free). Unknown/absent locale → `"vi"`, validated against `app.core.locale.SUPPORTED_LOCALES` (`{vi,en,zh,fr}`).
- Domain (`app/domain/**`) stays framework/SDK-free (the port is a plain Protocol).
- Branch `feat/auth-password-reset-locale` (already checked out). Do NOT `git add -A`. Run `./scripts/check.sh` before each commit (pgdb up). Commands from `backend/`.

---

### Task 1: `POST /auth/forgot-password` (trigger the reset email)

**Files:**
- Modify: `app/domain/auth/identity_provider.py` (port: `send_password_reset`)
- Modify: `app/infrastructure/supabase_identity_provider.py` (adapter impl)
- Modify: `app/application/auth/handlers.py` (`AuthSessionService.send_password_reset`)
- Modify: `app/api/v1/auth.py` (route + logger + imports)
- Modify: `app/schemas/auth.py` (`ForgotPasswordRequest`)
- Modify: `app/core/config.py`, `.env.example` (`PASSWORD_RESET_REDIRECT_URL`)
- Modify: `app/i18n/{vi,en,zh,fr}.json` (`auth.password_reset_sent`)
- Modify: `docs/contracts/rest-auth-api.md`
- Test: `tests/unit/test_forgot_password.py` (new); `tests/unit/test_password_reset_adapter.py` (new)

**Interfaces:**
- Produces: `IdentityProvider.send_password_reset(*, email: str) -> None`; `AuthSessionService.send_password_reset(*, email: str) -> None`; `POST /api/v1/auth/forgot-password` returning `{"data": {"message": <localized>}}` (200 always).

- [ ] **Step 1: Write the failing route tests** — create `tests/unit/test_forgot_password.py`:

```python
"""forgot-password is 200-always and non-enumerating (no existence/provider leak)."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.dependencies import get_auth_session_service
from app.main import create_app
from app.services.translator import load_translations


def _client(send_mock: AsyncMock) -> TestClient:
    app = create_app()

    class _Svc:
        send_password_reset = send_mock

    app.dependency_overrides[get_auth_session_service] = lambda: _Svc()
    return TestClient(app)


def test_forgot_password_returns_200_and_calls_service() -> None:
    load_translations()
    send = AsyncMock()
    resp = _client(send).post("/api/v1/auth/forgot-password", json={"email": "a@example.com"})
    assert resp.status_code == 200
    body = resp.json()["data"]
    # localized, not the raw key
    assert body["message"] and body["message"] != "auth.password_reset_sent"
    send.assert_awaited_once()
    assert send.await_args.kwargs == {"email": "a@example.com"}


def test_forgot_password_swallows_provider_error_still_200() -> None:
    load_translations()
    send = AsyncMock(side_effect=RuntimeError("provider down"))
    resp = _client(send).post("/api/v1/auth/forgot-password", json={"email": "x@example.com"})
    assert resp.status_code == 200  # never leak provider state
    assert resp.json()["data"]["message"] != "auth.password_reset_sent"


def test_forgot_password_rejects_bad_email() -> None:
    resp = _client(AsyncMock()).post("/api/v1/auth/forgot-password", json={"email": "not-an-email"})
    assert resp.status_code == 422  # Pydantic EmailStr validation
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_forgot_password.py -v`
Expected: FAIL — 404 (route not registered) on the 200 tests.

- [ ] **Step 3: Add the port method** — in `app/domain/auth/identity_provider.py`, add to the `IdentityProvider` Protocol (after `update_user`):

```python
    async def send_password_reset(self, *, email: str) -> None:
        """Best-effort: send a password-reset (recovery) email via the provider.

        Completion (verifying the recovery token + setting the new password) happens
        client-side via the provider SDK — this only triggers the email."""
        ...
```

- [ ] **Step 4: Implement the adapter** — in `app/infrastructure/supabase_identity_provider.py`: add `import asyncio` at the top (with the stdlib imports), and add the method to `SupabaseIdentityProvider`:

```python
    async def send_password_reset(self, *, email: str) -> None:
        # Anon client (no service role needed); off-loaded — the SDK call is blocking.
        # Pass redirect_to only when configured; otherwise Supabase uses the project
        # Site URL. Completion is client-side (verify_otp recovery + update_user).
        opts: dict[str, Any] = {}
        if settings.PASSWORD_RESET_REDIRECT_URL:
            opts["redirect_to"] = settings.PASSWORD_RESET_REDIRECT_URL
        await asyncio.to_thread(get_anon_client().auth.reset_password_email, email, opts)
```

(`get_anon_client`, `settings`, `Any` are already imported in this module — verify; add `Any` from typing if missing.)

- [ ] **Step 5: Add the service method** — in `app/application/auth/handlers.py`, add to `AuthSessionService`:

```python
    async def send_password_reset(self, *, email: str) -> None:
        """Trigger a provider password-reset email (best-effort)."""
        await self._identity.send_password_reset(email=email)
```

- [ ] **Step 6: Add the schema** — in `app/schemas/auth.py` (after `RefreshRequest`):

```python
class ForgotPasswordRequest(BaseModel):
    email: EmailStr
```

- [ ] **Step 7: Add the route** — in `app/api/v1/auth.py`: add `import logging` and after the imports `logger = logging.getLogger(__name__)`; add `ForgotPasswordRequest` to the `app.schemas.auth` import list; add the route (place it after `refresh_token`):

```python
@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    svc: AuthSessionService = Depends(get_auth_session_service),
) -> dict[str, Any]:
    """Trigger a password-reset email. ALWAYS returns 200 with the same message,
    regardless of whether the email exists or the provider is reachable — never leak
    account existence or provider state. Reset completion happens client-side via the
    Supabase SDK (verify recovery token + update password)."""
    try:
        await svc.send_password_reset(email=body.email)
    except Exception as e:
        logger.warning("forgot-password: provider call failed (swallowed): %s", e)
    return {"data": {"message": t("auth.password_reset_sent")}}
```

- [ ] **Step 8: Add config + env** — in `app/core/config.py`, add near `NOTIFICATION_CRON_HOUR`:

```python
    PASSWORD_RESET_REDIRECT_URL: str = ""  # web reset page; empty → Supabase Site URL
```

In `.env.example`, add:
```
PASSWORD_RESET_REDIRECT_URL=        # e.g. https://app.example.com/reset-password (empty → Supabase Site URL)
```

- [ ] **Step 9: Add i18n** — in each `app/i18n/{vi,en,zh,fr}.json`, add next to the other `auth.*` keys:
```
vi: "auth.password_reset_sent": "Nếu email này đã đăng ký, chúng tôi đã gửi liên kết đặt lại mật khẩu."
en: "auth.password_reset_sent": "If that email is registered, we've sent a password-reset link."
zh: "auth.password_reset_sent": "如果该邮箱已注册，我们已发送密码重置链接。"
fr: "auth.password_reset_sent": "Si cet e-mail est enregistré, nous avons envoyé un lien de réinitialisation."
```

- [ ] **Step 10: Write the adapter test** — create `tests/unit/test_password_reset_adapter.py`:

```python
"""send_password_reset off-loads the SDK call and passes redirect_to only when set."""

from unittest.mock import MagicMock

import pytest

import app.infrastructure.supabase_identity_provider as mod


@pytest.mark.asyncio
async def test_passes_redirect_to_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    monkeypatch.setattr(mod, "get_anon_client", lambda: client)
    monkeypatch.setattr(mod.settings, "PASSWORD_RESET_REDIRECT_URL", "https://app.example/reset")
    await mod.SupabaseIdentityProvider().send_password_reset(email="a@example.com")
    client.auth.reset_password_email.assert_called_once_with(
        "a@example.com", {"redirect_to": "https://app.example/reset"}
    )


@pytest.mark.asyncio
async def test_omits_redirect_to_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    monkeypatch.setattr(mod, "get_anon_client", lambda: client)
    monkeypatch.setattr(mod.settings, "PASSWORD_RESET_REDIRECT_URL", "")
    await mod.SupabaseIdentityProvider().send_password_reset(email="a@example.com")
    client.auth.reset_password_email.assert_called_once_with("a@example.com", {})
```

- [ ] **Step 11: Document the contract** — in `docs/contracts/rest-auth-api.md`, add a row/section for `POST /auth/forgot-password`: "200 always (non-enumerating); triggers a Supabase recovery email. Reset **completion is client-side**: the email link opens the web/mobile app with a `token_hash`/`type=recovery`; the client calls the Supabase SDK `verify_otp({type:'recovery', token_hash})` then `update_user({password})`. The backend has no `reset-password` endpoint by design." Match the doc's existing table/section style.

- [ ] **Step 12: Run tests + gate**

Run: `uv run pytest tests/unit/test_forgot_password.py tests/unit/test_password_reset_adapter.py tests/test_auth.py -v` then `./scripts/check.sh`
Expected: all PASS; `Gate passed.` (If the gotrue SDK signature rejects a positional `{}` opts, adjust the adapter to call `reset_password_email(email)` when opts is empty and update `test_omits_redirect_to_when_empty` accordingly — verify against the installed SDK.)

- [ ] **Step 13: Commit**

```bash
git add app/domain/auth/identity_provider.py app/infrastructure/supabase_identity_provider.py app/application/auth/handlers.py app/api/v1/auth.py app/schemas/auth.py app/core/config.py .env.example app/i18n/vi.json app/i18n/en.json app/i18n/zh.json app/i18n/fr.json docs/contracts/rest-auth-api.md tests/unit/test_forgot_password.py tests/unit/test_password_reset_adapter.py
git commit -m "feat(backend): POST /auth/forgot-password (200-swallow, non-enumerating) (auth)"
```

---

### Task 2: Populate `user_profiles.language` from the JWT in `ensure_user_profile`

**Files:**
- Modify: `app/core/security.py` (`ensure_user_profile` create + refresh branches; import `SUPPORTED_LOCALES`)
- Test: `tests/integration/test_ensure_user_profile_locale.py` (new)

**Interfaces:**
- Consumes: `app.core.locale.SUPPORTED_LOCALES` (`{vi,en,zh,fr}`), the existing `pg_insert` upsert in the create branch.

- [ ] **Step 1: Write the failing test** — create `tests/integration/test_ensure_user_profile_locale.py`:

```python
"""ensure_user_profile syncs user_profiles.language from the JWT's preferred_locale."""

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import ensure_user_profile


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


def _jwt(user_id: uuid.UUID, locale: str | None) -> dict[str, Any]:
    meta: dict[str, Any] = {"full_name": "L Tester"}
    if locale is not None:
        meta["preferred_locale"] = locale
    return {"sub": str(user_id), "email": f"loc-{user_id.hex[:8]}@example.com", "user_metadata": meta}


async def _language(maker: async_sessionmaker[AsyncSession], user_id: uuid.UUID) -> str | None:
    async with maker() as s:
        return await s.scalar(
            sa.text("SELECT language FROM user_profiles WHERE id = :id"), {"id": user_id}
        )


@pytest.mark.asyncio
async def test_first_login_sets_language_from_jwt(engine: AsyncEngine) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    uid = uuid.uuid4()
    async with maker() as db:
        await ensure_user_profile(_jwt(uid, "en"), db)
    assert await _language(maker, uid) == "en"


@pytest.mark.asyncio
async def test_refresh_updates_changed_language(engine: AsyncEngine) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    uid = uuid.uuid4()
    async with maker() as db:
        await ensure_user_profile(_jwt(uid, "en"), db)
    async with maker() as db:
        await ensure_user_profile(_jwt(uid, "zh"), db)
    assert await _language(maker, uid) == "zh"


@pytest.mark.asyncio
async def test_unknown_or_absent_locale_defaults_vi(engine: AsyncEngine) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    uid = uuid.uuid4()
    async with maker() as db:
        await ensure_user_profile(_jwt(uid, "de"), db)   # unsupported
    assert await _language(maker, uid) == "vi"
    uid2 = uuid.uuid4()
    async with maker() as db:
        await ensure_user_profile(_jwt(uid2, None), db)  # absent
    assert await _language(maker, uid2) == "vi"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integration/test_ensure_user_profile_locale.py -v`
Expected: FAIL — the create/refresh branches never set `language`, so it stays the model default `"vi"`; `test_first_login_sets_language_from_jwt` (expects `en`) and `test_refresh_updates_changed_language` (expects `zh`) fail.

- [ ] **Step 3: Add a locale helper + wire the create branch** — in `app/core/security.py`, add `from app.core.locale import SUPPORTED_LOCALES` to the imports, and a small module-level helper above `ensure_user_profile`:

```python
def _jwt_language(current_user: dict[str, Any]) -> str:
    """The recipient's chosen locale from the JWT metadata, validated (unknown → 'vi')."""
    loc = current_user.get("user_metadata", {}).get("preferred_locale")
    return loc if loc in SUPPORTED_LOCALES else "vi"
```

In the create branch, add `language=_jwt_language(current_user)` to the `pg_insert(UserProfile).values(...)`:

```python
        stmt = (
            pg_insert(UserProfile)
            .values(
                id=user_id,
                email=email,
                display_name=display_name,
                language=_jwt_language(current_user),
                last_login_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
```

- [ ] **Step 4: Wire the refresh branch** — replace the existing else-branch throttle block with one that also syncs language and commits when EITHER changed:

```python
    else:
        now = datetime.now(UTC)
        changed = False
        desired_language = _jwt_language(current_user)
        if profile.language != desired_language:
            profile.language = desired_language
            changed = True
        if (
            profile.last_login_at is None
            or (now - profile.last_login_at).total_seconds() > _LOGIN_UPDATE_INTERVAL
        ):
            profile.last_login_at = now
            changed = True
        if changed:
            await db.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_ensure_user_profile_locale.py tests/integration/test_ensure_user_profile_commit.py -v`
Expected: PASS (the A1 commit/idempotency/deactivation tests stay green — language is additive).

- [ ] **Step 6: Full gate**

Run: `./scripts/check.sh`
Expected: `Gate passed.`

- [ ] **Step 7: Commit**

```bash
git add app/core/security.py tests/integration/test_ensure_user_profile_locale.py
git commit -m "feat(backend): sync user_profiles.language from JWT in ensure_user_profile (auth; activates PR-H locale)"
```

---

## Self-review notes (author)

- **Spec coverage:** forgot-password (port/adapter/service/route/schema/config/i18n/contract) → Task 1; 200-swallow + non-enumeration → Task 1 route + tests; `user_profiles.language` sync (create + refresh, unknown→vi) → Task 2. Email verification, backend reset-completion, immediate PATCH /me write — all in the spec's out-of-scope, correctly absent here.
- **Type consistency:** `send_password_reset(*, email: str) -> None` identical across port/adapter/service; `_jwt_language(current_user) -> str` used in both branches; `ForgotPasswordRequest.email: EmailStr`.
- **YAGNI:** no reset-password endpoint, no email verification, no MFA — matches the approved spec.
- **SDK caveat flagged:** Step 12 notes verifying the gotrue `reset_password_email` empty-opts call against the installed SDK (adjust if it rejects a positional `{}`).
