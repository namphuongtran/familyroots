# Production Hardening Design Spec

**Date:** 2026-07-14
**Branch:** `feat/production-hardening` (off `main` @ 4cfec1a)
**Purpose:** Close the last code-side production-hardening gaps from the 2026-07-12
deep review before frontend work starts: the register endpoint is the one remaining
account-enumeration oracle, `audit_logs.ip_address`/`user_agent` are NULL by
construction (useless forensics), and the invitation-accept endpoint is the one
sensitive unauthenticated-adjacent surface outside the rate limiter.

**Owner decision (2026-07-14):** register becomes **non-enumerating with an email
nudge** (OWASP style), accepting the response-contract change while no frontend
exists.

---

## Item 1 — Non-enumerating register + email nudge

### Current behavior (verified)
`AuthCommandHandler.register` (`app/application/auth/handlers.py:214-215`) maps
`IdentityUserExistsError` → 409 `auth.email_already_exists` — the only remaining
auth surface that confirms account existence (forgot-password and
resend-verification are already non-enumerating). Single raise site; the i18n key
exists in all 4 locales; `POST /onboard` does NOT share this path (it is
authenticated — no enumeration concern — and keeps its current rich response).

### New contract (breaking, pre-frontend)
`POST /auth/register` returns **the identical body for both paths**:

```json
201  { "data": { "message": "<i18n auth.registration_received>" } }
```

- No `user_id`/`clan_id`/`is_approved`/`email` in the response. The client always
  routes to a "check your email" screen; real state arrives after verify + login
  (which already returns the full profile). `RegisterResponse` stays for
  `/onboard` only.
- **New email** → existing flow unchanged internally (create identity unconfirmed →
  clan assignment with compensation → best-effort verification email).
- **Existing email** → create nothing; **best-effort** send a recovery email to the
  owner via the existing `send_password_reset` seam ("you already have an account —
  reset your password if you forgot it" is Supabase's recovery mail); swallow
  send errors exactly like the other non-enumerating endpoints; return the same
  201 body.
- Validation errors that do NOT leak account existence keep their current codes
  (422 `auth.password_too_weak`, `auth.registration_failed`, clan-field
  validation, 409 `auth.clan_slug_taken` — slug existence is public, not an
  account oracle; 503 `identity_unavailable` unchanged).
- `auth.email_already_exists` is removed from the register path → the error code
  and all 4 i18n entries are deleted (single raise site verified; the i18n
  coverage test enforces no orphans in either direction — confirm its direction
  semantics and satisfy it).
- New i18n key ×4 locales: `auth.registration_received` (vi: "Đăng ký đã được
  tiếp nhận — vui lòng kiểm tra email của bạn.").
- **Residual accepted risk (document in ADR):** timing side-channel (the two paths
  do different work) — mitigated by the 20/min/IP auth rate limit; not worth
  constant-time engineering at this threat model.

### Docs in the same PR
`rest-auth-api.md` (register response + both-paths note), `error-codes.md` (remove
the code row; note non-enumeration now covers register), `frontend-integration-
guide.md` (register → always check-email screen), **ADR-021** (auth surfaces are
uniformly non-enumerating: register/forgot-password/resend-verification; nudge
mechanism; timing residual; contract change rationale).

### Testing
- Both paths return byte-identical status+body (the load-bearing assertion).
- Existing-email path: NO user/clan/membership/identity created (DB + identity-spy
  assertions), recovery email sent exactly once (spy), send-failure still returns
  the same 201 (swallow test — mirror the resend-verification swallow test).
- New-email path: full flow regression (existing register tests re-pointed to the
  new response shape).
- Onboard response unchanged (regression).

## Item 2 — Audit rows carry ip_address / user_agent

### Current behavior (verified)
`audit_logs.ip_address` (INET) and `user_agent` columns exist since migration 001
but `AuditLogHandler` (`app/infrastructure/event_dispatcher.py:75-86`) never sets
them — NULL on every row.

### Design
- New `app/core/request_meta.py`: a `ContextVar[RequestMeta | None]`
  (`RequestMeta = {ip: str | None, user_agent: str | None}`) + tiny pure helpers
  `set_request_meta/get_request_meta/reset_request_meta`.
- New middleware `RequestMetaMiddleware` (registered next to LanguageMiddleware in
  `main.py`): resolves the client IP with the SAME proxy logic and the SAME
  `RATE_LIMIT_TRUST_FORWARDED_FOR` switch the rate limiter uses (extract the
  shared helper from `app/core/rate_limit.py` rather than duplicating it);
  captures `User-Agent` truncated to the column length (check the model; 255 if
  unspecified); sets the ContextVar for the request scope and resets after.
- `AuditLogHandler.handle` reads the ContextVar and passes
  `ip_address=meta.ip, user_agent=meta.user_agent` (both None outside a request —
  scheduler/purge jobs correctly write NULL).
- Layering: `infrastructure → core` import is legal; the domain layer stays
  untouched (events don't carry transport data — the handler enriches at write
  time).

### Testing
- HTTP mutation (e.g. create person) → its audit row has the client IP + UA.
- `X-Forwarded-For` honored ONLY when the trust flag is on (both directions
  tested — mirror the rate limiter's existing proxy tests).
- Scheduler-driven audit writes (or a direct dispatcher call outside request
  scope) → NULL ip/ua.
- UA longer than the column → truncated, no DB error.

## Item 3 — Rate-limit the invitation-accept surface

### Current behavior (verified)
`RateLimitMiddleware` takes a single `path_prefix="/api/v1/auth"`
(`app/core/rate_limit.py:38`); `POST /api/v1/invitations/{token}/accept` is
unthrottled — the only brute-forceable token surface outside the limiter (256-bit
tokens make success implausible, but unthrottled probing is still noise/abuse).

### Design
`path_prefix: str` → `path_prefixes: tuple[str, ...]` (default
`("/api/v1/auth",)`); match = `any(path.startswith(p) ...)`. `main.py` passes
`("/api/v1/auth", "/api/v1/invitations")`. Same limiter instance, same 20/min/IP
bucket and Retry-After semantics. Admin invitation CRUD lives under
`/api/v1/clans/{id}/invitations` — NOT covered (authenticated admin surface, out
of scope; note in the ADR).

### Testing
Burst on `/invitations/{token}/accept` → 429 + `Retry-After` + `detail.retry_after`;
auth paths still limited (regression); an uncovered path (e.g. `/persons`) never
throttled.

## Item 4 — `engine.dispose()` on shutdown
One-liner in `main.py`'s lifespan finally (after scheduler stop): dispose the
async engine so connections close cleanly on SIGTERM. Covered by existing
lifespan/startup tests still passing (no dedicated new test).

## Explicitly NOT in this pass
Redis-backed rate limiting; request-ID middleware; CAPTCHA; onboard-flow changes;
Sentry wiring and render.yaml env population (owner/infra actions, tracked in
configuration.md); freshness dead-man's-switch (PR2 follow-up).

## Quality gates
Full backend gate; i18n coverage test green after key add/remove; contracts docs
updated in the same PR; ADR-021 in the same PR.
