# Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register stops leaking account existence (uniform 201 + recovery-email nudge), audit rows carry ip/user-agent, invitation-accept joins the rate limiter, and the engine disposes cleanly on shutdown.

**Architecture:** Spec = `docs/superpowers/specs/2026-07-14-production-hardening-design.md`. Register's `IdentityUserExistsError` branch flips from 409 to a silent `send_password_reset` nudge + the same generic 201 both paths return. A `RequestMeta` ContextVar (set by a new middleware, IP resolved by a helper EXTRACTED from the rate limiter so both share one proxy-trust switch) is read by `AuditLogHandler` at write time — domain events stay transport-free. `RateLimitMiddleware` takes a prefix tuple.

**Tech Stack:** Existing FastAPI/SQLAlchemy/pytest stack; no new dependencies, no migrations.

## Global Constraints

- Quality gate after EVERY task (from `backend/`): `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` (mypy via `uv run`, never `uvx mypy`).
- Handlers raise `app.domain.shared.exceptions.*` only; import-linter ratchet must not grow.
- i18n: remove `error.auth.email_already_exists` from ALL FOUR `app/i18n/{vi,en,fr,zh}.json`; add `auth.registration_received` to all four (vi: `"Đăng ký đã được tiếp nhận — vui lòng kiểm tra email của bạn."`; natural en/fr/zh). `tests/unit/test_i18n_coverage.py` must stay green (it asserts raised-codes ⊆ vi keys + 4-locale parity).
- The uniform register body is THE contract: both paths byte-identical `{"data": {"message": <t("auth.registration_received")>}}`, status 201.
- `POST /onboard` response unchanged.
- Audit columns: `ip_address` INET (plain string ok), `user_agent` String(500) — truncate UA to 500.
- One proxy-trust switch: `settings.RATE_LIMIT_TRUST_FORWARDED_FOR` governs BOTH the rate limiter and RequestMeta IP resolution (rightmost-XFF rule, exactly the current `_client_ip` semantics).
- Never `git add -A`. Postgres pgdb up for integration tests.

---

### Task 1: Non-enumerating register + email nudge

**Files:**
- Modify: `backend/app/application/auth/handlers.py:200-250` (`register`)
- Modify: `backend/app/api/v1/auth.py:40-54` (register route)
- Modify: `backend/app/schemas/auth.py` ONLY if `RegisterResponse` needs a comment noting it is onboard-only now (do not delete it — onboard uses it)
- Modify: `backend/app/i18n/{vi,en,fr,zh}.json` (remove old error key; add `auth.registration_received`)
- Test: `backend/tests/integration/test_register_non_enumeration.py` (new) + re-point every existing test asserting the old register response/409 (grep: `tests/integration/test_auth_http_flow.py`, `test_auth_provisioning.py`, `tests/unit/application/test_auth_register_compensation.py`, `tests/integration/test_phase0_blockers.py` — read each first)

**Interfaces:**
- Consumes: existing `self._identity.send_password_reset(email=...)` seam (already used by `forgot_password` at `handlers.py:76-78`) and `IdentityUserExistsError`.
- Produces: `AuthCommandHandler.register(...) -> None` (no longer returns `RegisterResponse`); the route builds the uniform body itself. Existing-email path calls `send_password_reset` best-effort (swallow ALL exceptions with a warning log — mirror how the verification-email best-effort path logs).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integration/test_register_non_enumeration.py
"""Register is non-enumerating (ADR-021): identical response whether or not the
email already has an account; existing accounts get a recovery-email nudge."""

import pytest

pytestmark = pytest.mark.integration

# Fixtures: the app client + identity-provider fake used by the existing register
# tests — READ tests/integration/test_auth_http_flow.py first and reuse its
# fixture pattern (fake identity provider records create_user / send_password_reset
# calls; if the existing fake lacks a send_password_reset recorder, extend it).

REGISTER_BODY_NEW = {
    "email": "moi@example.com", "password": "S3cure!pass", "full_name": "Người Mới",
    "clan_action": "create", "clan_name": "Họ Mới", "clan_slug": "ho-moi",
}


async def test_both_paths_return_identical_body(client, identity_fake, seeded_existing_email):
    fresh = await client.post("/api/v1/auth/register", json=REGISTER_BODY_NEW)
    dup_body = {**REGISTER_BODY_NEW, "email": seeded_existing_email, "clan_slug": "ho-khac"}
    dup = await client.post("/api/v1/auth/register", json=dup_body)
    assert fresh.status_code == dup.status_code == 201
    assert fresh.json() == dup.json()                      # byte-identical envelope
    assert set(fresh.json()["data"].keys()) == {"message"}  # no ids leak


async def test_existing_email_creates_nothing_and_nudges(client, identity_fake, seeded_existing_email, db_session):
    before_users = await _count(db_session, "user_profiles")
    before_clans = await _count(db_session, "clans")
    resp = await client.post("/api/v1/auth/register", json={**REGISTER_BODY_NEW, "email": seeded_existing_email})
    assert resp.status_code == 201
    assert identity_fake.create_user_calls_for(seeded_existing_email) == 0
    assert identity_fake.password_reset_calls_for(seeded_existing_email) == 1
    assert await _count(db_session, "user_profiles") == before_users
    assert await _count(db_session, "clans") == before_clans


async def test_nudge_failure_still_returns_same_201(client, identity_fake, seeded_existing_email):
    identity_fake.fail_password_reset = True
    resp = await client.post("/api/v1/auth/register", json={**REGISTER_BODY_NEW, "email": seeded_existing_email})
    assert resp.status_code == 201
    assert set(resp.json()["data"].keys()) == {"message"}


async def test_new_email_full_flow_still_works(client, identity_fake, db_session):
    resp = await client.post("/api/v1/auth/register", json=REGISTER_BODY_NEW)
    assert resp.status_code == 201
    assert identity_fake.create_user_calls_for(REGISTER_BODY_NEW["email"]) == 1
    # clan + membership actually created (query by slug)


async def test_onboard_response_unchanged(client, ...):
    # regression: onboard still returns user_id/clan_id/... (reuse existing onboard test setup)
    ...
```

Write `_count` and the fixtures concretely from the existing test files' patterns; replace the `...` stubs with the real setup those files already use (this is re-pointing, not invention).

- [ ] **Step 2: Run to verify failure** — identical-body test fails (dup path currently 409). `cd backend && uv run pytest tests/integration/test_register_non_enumeration.py -q`
- [ ] **Step 3: Implement**

`handlers.py::register` — replace the `IdentityUserExistsError` branch and the return:

```python
        try:
            user_id_str = await self._identity.create_user(email=email, password=password)
        except IdentityUserExistsError:
            # Non-enumerating register (ADR-021): an existing account gets a silent
            # recovery-email nudge; the caller sees the same 201 as a fresh signup.
            try:
                await self._identity.send_password_reset(email=email)
            except Exception:  # noqa: BLE001 — nudge is best-effort by design
                logger.warning("register nudge: password-reset send failed", exc_info=True)
            return
        ...existing flow unchanged, but drop the final `return response` /
        RegisterResponse construction — the method returns None on success too...
```

Adjust the signature to `-> None` and delete the now-unused RegisterResponse import/build in this method (VERIFY `_assign_clan_membership`'s return is still needed internally — read it; keep internals, drop only the response surface). Route:

```python
@router.post("/register", status_code=201)
async def register(
    body: RegisterRequest, handler: AuthCommandHandler = Depends(get_auth_command_handler)
) -> dict[str, Any]:
    """Register — always the same response whether or not the email has an account
    (non-enumerating, ADR-021). Real state arrives after email verify + login."""
    await handler.register(
        email=body.email, password=body.password, full_name=body.full_name,
        clan_action=body.clan_action, clan_id=body.clan_id,
        clan_name=body.clan_name, clan_slug=body.clan_slug,
    )
    return {"data": {"message": t("auth.registration_received")}}
```

i18n: remove `error.auth.email_already_exists` ×4, add `auth.registration_received` ×4. Re-point existing tests (never delete assertions — flip them to the new contract; the compensation unit test's assertions about compensation behavior stay, only response-shape expectations change).

- [ ] **Step 4: Run the new file + all re-pointed files + i18n coverage** — then full suite.
- [ ] **Step 5: Full gate, commit**

```bash
git add backend/app backend/tests
git commit -m "feat(backend): non-enumerating register with recovery-email nudge (ADR-021)"
```

---

### Task 2: Audit rows carry ip_address / user_agent

**Files:**
- Create: `backend/app/core/request_meta.py`
- Create: `backend/app/middleware/request_meta_middleware.py`
- Modify: `backend/app/core/rate_limit.py:53-67` (`_client_ip` → delegate to the shared helper)
- Modify: `backend/app/infrastructure/event_dispatcher.py:75-86` (`AuditLogHandler.handle`)
- Modify: `backend/app/main.py` (~line 164, register the middleware next to LanguageMiddleware)
- Test: `backend/tests/integration/test_audit_request_meta.py` (new) + `tests/unit/test_rate_limit*.py` regression (grep for the existing rate-limit tests and run them)

**Interfaces:**
- Produces: `app/core/request_meta.py`:

```python
"""Request-scoped transport metadata for audit enrichment (spec 2026-07-14).

Domain events stay transport-free; AuditLogHandler enriches at write time from
this ContextVar. Outside a request (scheduler/purge jobs) it is None -> NULL
columns, which is the correct semantics for system-initiated changes.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestMeta:
    ip: str | None
    user_agent: str | None


_request_meta: ContextVar[RequestMeta | None] = ContextVar("request_meta", default=None)


def set_request_meta(meta: RequestMeta) -> object:
    return _request_meta.set(meta)


def get_request_meta() -> RequestMeta | None:
    return _request_meta.get()


def reset_request_meta(token: object) -> None:
    _request_meta.reset(token)  # type: ignore[arg-type]


def resolve_client_ip(headers_get, client_host: str | None, trust_xff: bool) -> str | None:
    """Rightmost-XFF rule shared with the rate limiter: only the entry appended
    by our single trusted proxy is trustworthy; leftmost entries are spoofable."""
    if trust_xff:
        xff = headers_get("x-forwarded-for")
        if xff:
            return xff.split(",")[-1].strip()
    return client_host
```

  (Signature takes `headers_get`/`client_host` primitives so it has no Starlette dependency and stays unit-testable; adapt if you prefer passing `Request` — but then it lives fine in core since core already imports Starlette in rate_limit. Choose ONE and keep both call sites on it.)
- Middleware `request_meta_middleware.py`: BaseHTTPMiddleware that computes `RequestMeta(ip=resolve_client_ip(...), user_agent=(request.headers.get("user-agent") or None) and truncated[:500])`, sets the ContextVar, `try/finally` resets. Trust flag from `settings.RATE_LIMIT_TRUST_FORWARDED_FOR`.
- `rate_limit.py::_client_ip` body becomes a call to `resolve_client_ip(...)` with a `or "unknown"` fallback (its bucket key must stay non-None) — behavior byte-identical, one copy of the XFF rule.
- `AuditLogHandler.handle` adds:

```python
        meta = get_request_meta()
        ...
            AuditLog(
                ...existing fields...,
                ip_address=meta.ip if meta else None,
                user_agent=meta.user_agent if meta else None,
            )
```

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integration/test_audit_request_meta.py
"""audit_logs rows carry the requester's ip/user-agent (spec 2026-07-14)."""
# Fixtures: reuse the HTTP fixture pattern (clan + editor) from an existing
# audit-writing test (grep tests/integration/test_audit_trail.py — read it first).

async def test_http_mutation_audit_row_has_ip_and_ua(client, editor_headers, db_session, clan_id):
    await client.post("/api/v1/persons", json={"full_name": "Cụ Test"}, headers={**editor_headers, "User-Agent": "FamilyRootsTest/1.0"})
    row = await _latest_audit(db_session, clan_id)
    assert row["user_agent"] == "FamilyRootsTest/1.0"
    assert row["ip_address"] is not None


async def test_xff_honored_only_when_trusted(client_trusting_proxy, client, ...):
    # trust ON: X-Forwarded-For "1.2.3.4, 5.6.7.8" -> audit ip == "5.6.7.8" (rightmost)
    # trust OFF (default client): same header -> audit ip == the direct peer, not 5.6.7.8
    ...


async def test_out_of_request_audit_rows_are_null(db_session, ...):
    # dispatch an AuditableEvent through create_event_dispatcher directly (no HTTP)
    # -> ip_address IS NULL AND user_agent IS NULL


async def test_long_user_agent_truncated(client, editor_headers, db_session, clan_id):
    ua = "X" * 800
    ... assert len(row["user_agent"]) == 500
```

Build `client_trusting_proxy` by constructing the app with the trust setting flipped — read how existing rate-limit trust tests do it (grep `TRUST_FORWARDED_FOR` under tests/) and mirror. Replace `...` with that concrete pattern.

- [ ] **Step 2: RED** — ip/ua currently always NULL.
- [ ] **Step 3: Implement** per Interfaces. Register middleware in `main.py` AFTER LanguageMiddleware registration line (Starlette middleware order note: add_middleware wraps outermost-last — placement next to LanguageMiddleware is fine; copy its style).
- [ ] **Step 4: Run new file + existing rate-limit tests (helper extraction regression) + audit-trail tests + full suite.**
- [ ] **Step 5: Full gate, commit**

```bash
git add backend/app backend/tests
git commit -m "feat(backend): audit rows carry client ip/user-agent via request-meta contextvar"
```

---

### Task 3: Rate-limit invitation accept + engine dispose

**Files:**
- Modify: `backend/app/core/rate_limit.py:38-44,98` (`path_prefix: str` → `path_prefixes: tuple[str, ...]`)
- Modify: `backend/app/main.py:152-160` (pass the tuple) and lifespan `finally` (~112-113: engine dispose after scheduler stop)
- Test: `backend/tests/integration/test_invitation_rate_limit.py` (new) + existing rate-limit tests re-pointed to the new param name

**Interfaces:**
- Consumes: Task 2's refactored `_client_ip` (unchanged signature).
- Produces: `RateLimitMiddleware(app, path_prefixes: tuple[str, ...] = ("/api/v1/auth",), ...)`; dispatch guard `if not any(request.url.path.startswith(p) for p in self._prefixes)`. `main.py` passes `path_prefixes=("/api/v1/auth", "/api/v1/invitations")`. Lifespan finally gains engine dispose — read the `_safe` helper first; `engine.dispose()` is ASYNC, so if `_safe` is sync-only, await it directly in its own try/except (mirror `_safe`'s logging style):

```python
        try:
            from app.core.database import engine
            await engine.dispose()
        except Exception:
            logger.exception("teardown step failed: engine-dispose")
```

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_invitation_rate_limit.py
"""POST /invitations/{token}/accept is rate-limited (spec 2026-07-14)."""

async def test_invitation_accept_throttled_after_burst(client_with_rate_limit, auth_headers):
    # Build the app with RateLimitMiddleware active (the default test app may omit
    # it — read how existing rate-limit integration tests construct their client
    # and mirror; low max_requests for test speed, e.g. 5).
    for _ in range(5):
        r = await client_with_rate_limit.post("/api/v1/invitations/deadbeef/accept", headers=auth_headers)
        assert r.status_code != 429
    r = await client_with_rate_limit.post("/api/v1/invitations/deadbeef/accept", headers=auth_headers)
    assert r.status_code == 429
    assert "retry-after" in {k.lower() for k in r.headers}
    assert r.json()["error"]["code"] == "rate_limited"


async def test_non_covered_path_not_throttled(client_with_rate_limit, auth_headers):
    for _ in range(10):
        r = await client_with_rate_limit.get("/api/v1/persons", headers=auth_headers)
        assert r.status_code != 429
```

- [ ] **Step 2: RED** (accept endpoint unthrottled today).
- [ ] **Step 3: Implement** the tuple param + main wiring + engine dispose. Update any existing tests/constructor calls using `path_prefix=`.
- [ ] **Step 4: Run new + existing rate-limit tests + app smoke (lifespan) + full suite.**
- [ ] **Step 5: Full gate, commit**

```bash
git add backend/app backend/tests
git commit -m "feat(backend): rate-limit invitation accept; dispose engine on shutdown"
```

---

### Task 4: ADR-021 + docs sweep

**Files:**
- Create: `docs/decisions/021-non-enumerating-auth-surfaces.md`
- Modify: `docs/decisions/README.md` (row 021)
- Modify: `docs/contracts/rest-auth-api.md` (register response uniform both paths; response-shapes section updated; onboard unchanged note)
- Modify: `docs/contracts/error-codes.md` (remove `auth.email_already_exists` row; registration section note: register is non-enumerating; add `auth.registration_received` is a MESSAGE not an error — no row needed, but the 401/403 matrix intro's Registration table must drop the dead code)
- Modify: `docs/contracts/frontend-integration-guide.md` (register → always route to check-email screen; existing-account users get a recovery email instead of an error)
- Modify: `docs/architecture/api-design.md` (auth table register row wording + invitations rate-limited note; the "only rate-limited scope" sentence must now say auth + invitations)
- Modify: `docs/architecture/auth-flow.md` (rate-limit scope sentence + register non-enumeration paragraph; it currently says "extending the scope to /invitations/*/accept is an open backlog item" — now shipped)
- Modify: `docs/architecture/rbac.md` / `docs/contracts/push-notifications.md` — ONLY if grep finds stale claims (`grep -rn "email_already_exists\|only.*rate-limited\|20 req/min" docs/` and judge each hit; docs/superpowers dated files are historical — skip)
- Test: none — full gate once as evidence.

**Interfaces:** Documents Tasks 1-3 actuals; verify every claim in code first.

- [ ] **Step 1: ADR-021** (house style of 017-020): all three account-existence surfaces (register/forgot-password/resend-verification) uniformly non-enumerating; the recovery-email nudge mechanism; response-contract change rationale (pre-frontend window); residual timing side-channel accepted (rate-limited); audit request-meta enrichment (ContextVar at write-time, domain stays transport-free); invitation-accept rate-limit scope (admin CRUD under /clans/{id}/invitations deliberately NOT covered — authenticated admin surface).
- [ ] **Step 2: Docs edits** per Files list, each claim verified against shipped code.
- [ ] **Step 3: Full gate; commit**

```bash
git add docs
git commit -m "docs: ADR-021 non-enumerating auth + hardening doc sweep"
```
