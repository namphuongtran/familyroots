# ADR-021: Non-Enumerating Auth Surfaces + Request-Meta Audit Enrichment + Invitation-Accept Rate Limit

## Status
Accepted (2026-07-14 — shipped).

## Context
The 2026-07-12 deep review left three gaps on the production-hardening backlog,
closed together in this PR (`feat/production-hardening`, off `main` @ `4cfec1a`):

1. **Register was the last account-enumeration oracle.** `forgot-password` and
   `resend-verification` were already non-enumerating (ADR-015), but
   `AuthCommandHandler.register` mapped `IdentityUserExistsError` → 409
   `auth.email_already_exists` — a status-code that confirms an email already
   has an account. Worse, clan-input validation (`clan_id_required_for_join`,
   `clan_name_required_for_create`, `clan_slug_taken`, `clan_not_found`) ran
   only *after* `create_user`, inside `_assign_clan_membership` — so a bad
   `clan_id`/`clan_slug` on a **fresh** email surfaced as 422/404, while the
   same bad input on an **existing** email never reached that code at all (it
   short-circuited at the 409 first). That divergence is itself a second,
   subtler oracle: an attacker could distinguish existing vs. fresh emails
   purely from which validation error came back, independent of the
   already-exists code.
2. **`audit_logs.ip_address`/`user_agent` were NULL by construction.**
   Both columns exist since migration 001 (INET + text), but
   `AuditLogHandler` never populated them — every forensic audit row was
   missing the transport context needed to investigate abuse.
3. **`POST /invitations/{token}/accept` was the one sensitive, token-bearing,
   unauthenticated-adjacent surface outside the rate limiter.** 256-bit
   tokens make brute-force success implausible, but unthrottled probing is
   still noise/abuse the limiter should absorb like it does for auth.

## Decision

### 1. Register is non-enumerating (uniform response + nudge)
`POST /auth/register` now returns **the identical 201 body regardless of
whether the email already has an account**:

```json
201 { "data": { "message": "<t('auth.registration_received')>" } }
```

- **Clan-input validation is hoisted before `create_user`** (`AuthCommandHandler.register`,
  `app/application/auth/handlers.py`). The `clan_action == "join"`/`"create"`
  checks and the `clan_slug_taken` / `clan_not_found` lookups run
  unconditionally, mirroring `_assign_clan_membership`'s checks exactly (same
  exceptions/codes), **before** the identity is ever created. This closes the
  status-code oracle described above: a bad clan input now fails identically
  whether or not the email exists, because the check runs before the code
  path can diverge on `IdentityUserExistsError`. `_assign_clan_membership`
  keeps its own copies of these checks as defense-in-depth for callers that
  reach it directly (`onboard_authenticated_user`, which is authenticated and
  has no enumeration concern).
- **New email**: unchanged internally — create identity unconfirmed → clan
  assignment with orphan-compensation on failure → best-effort verification
  email (ADR-015).
- **Existing email** (`IdentityUserExistsError`): create nothing; send a
  **best-effort recovery email** via the existing `send_password_reset` seam
  (Supabase's password-reset mail doubles as an "you already have an
  account" nudge) and return the same 201. Send failures are swallowed
  exactly like the other non-enumerating endpoints (logged at `warning`, never
  surfaced to the caller).
- `auth.email_already_exists` is **removed** — the single raise site is gone,
  the error-code row is deleted, and all four i18n locale entries are
  deleted (the i18n coverage test enforces no orphaned keys in either
  direction).
- New i18n key `auth.registration_received`, all four locales — deliberately
  phrased account-agnostic ("if that email is valid, you'll receive next
  steps shortly" / vi: "Nếu email hợp lệ, bạn sẽ sớm nhận được hướng dẫn tiếp
  theo"), not "registration received", so the message itself never confirms
  which branch ran.
- Validation errors that do **not** leak account existence are unchanged and
  stay symmetric on both paths: 422 `auth.password_too_weak`,
  `auth.registration_failed`, `auth.clan_id_required_for_join`,
  `auth.clan_name_required_for_create`; 409 `auth.clan_slug_taken` (slug
  existence is public — a clan lookup, not an account oracle); 404
  `clan_not_found`; 503 `auth_provider_unavailable`. These are returned
  identically regardless of whether the email exists, which is exactly the
  property the reordering above guarantees.

**Breaking response-contract change, accepted pre-frontend.** `RegisterResponse`
(`user_id`/`email`/`clan_id`/`is_approved`/`message`) is no longer returned by
`POST /auth/register` — it is now onboard-only (`POST /auth/onboard`, an
authenticated surface with no enumeration concern, keeps the full shape via
`_assign_clan_membership`). The client always routes register to a
"check your email" screen; real profile state arrives after email-verify +
login, which already returns the full profile. This is a breaking change to
`docs/contracts/rest-auth-api.md`, deliberately taken now because no frontend
consumes the current shape yet — the cost of the migration is zero today and
grows every day it's deferred.

**Residual accepted risk — timing side-channel.** The two branches
(create-identity-and-assign-clan vs. send-password-reset) do measurably
different work, so response latency could in principle distinguish existing
vs. fresh emails. This is accepted, not mitigated with constant-time
engineering, because: (a) the endpoint is rate-limited to 20 req/min/IP
(Decision 3 below), making a timing-oracle campaign slow and noisy; (b) the
attacker still learns nothing actionable beyond "an account with this email
exists," which is also learnable via the (unavoidable) login/forgot-password
timing surface any auth system has; (c) this repo's threat model (a
multi-clan genealogy platform, not a financial system) doesn't justify the
engineering cost of constant-time branches here. Revisit if a future threat
model demands it.

**Residual accepted risk — weak-password status divergence.** `register()`
defers the existing-vs-weak-password decision entirely to the identity
provider's `create_user`: whichever `IdentityError` subclass it raises first
determines the branch, and the two checks (email-exists, password-strength)
are not both re-run app-side. If Supabase's GoTrue checks duplicate-email
*before* password-strength inside the admin `create_user` call, a
Pydantic-valid (>=8 char) but policy-weak password produces a **422**
`auth.password_too_weak` for a fresh email but the uniform **201** nudge for
an existing email — a status/body enumeration oracle, structurally
equivalent to the one Decision 1 closed for clan-input validation. This is:
(a) **unreachable under Supabase's default password policy** — the default
minimum length is 6, and our Pydantic schema already requires >=8 chars, so
no password the app accepts as input can ever be "weak" by the default
policy; (b) **reachable only if an operator tightens** the deployed
project's Supabase password policy past our 8-char floor (or adds other
strength rules) **and** GoTrue's `create_user` checks existence before
strength — that ordering is **unverified**: historically the admin
`create_user` endpoint didn't enforce the password-strength policy at all,
so its behavior once a project *does* enable strength enforcement on that
path hasn't been confirmed against Supabase's source or changelog; (c)
**mitigated** by the existing 20 req/min/IP auth rate limit (Decision 3),
which bounds probing speed even if reachable; (d) **not worth closing
structurally** — doing so would mean replicating Supabase's password policy
app-side (duplicating provider-owned, operator-configurable config,
guaranteed to drift) purely to preserve a guarantee against a threat that is
gated behind an operator opting into a stricter policy than the default, and
we can't return 201 for a genuinely weak fresh signup without silently
dropping the user. Accepted as-is, pinned by regression tests in
`backend/tests/integration/test_register_non_enumeration.py`; revisit if
this project's Supabase password policy is ever tightened past the default.
**Provider-unavailable (503) remains symmetric**: `create_user` raising
`IdentityUnavailableError` happens before either check can run, so both a
fresh and an existing email get an identical 503 — this is verified by
`test_provider_unavailable_symmetric`, not merely assumed.

### 2. Audit rows carry `ip_address` / `user_agent` at write time
- **New `app/core/request_meta.py`**: a `ContextVar[RequestMeta | None]`
  (`RequestMeta = {ip, user_agent}`) with pure `set_request_meta` /
  `get_request_meta` / `reset_request_meta` helpers, plus `resolve_client_ip`
  — the same rightmost-XFF-wins proxy logic `RateLimitMiddleware` already
  used, extracted so both middlewares share one implementation instead of two
  copies drifting apart.
- **New `RequestMetaMiddleware`** (`app/middleware/request_meta_middleware.py`,
  registered in `main.py` next to `LanguageMiddleware`): resolves the client
  IP with the same `RATE_LIMIT_TRUST_FORWARDED_FOR` switch the rate limiter
  uses, validates it's a real IP literal before it can reach the `INET`
  column (`_validated_ip` — rejects things like TestClient's `"testclient"`
  placeholder or a malformed XFF value, logging a warning rather than letting
  Postgres reject the INSERT and abort the whole audit-write transaction),
  truncates `User-Agent` to 500 chars, sets the ContextVar for the request's
  duration, and resets it in a `finally`.
- **`AuditLogHandler.handle`** (`app/infrastructure/event_dispatcher.py`) reads
  the ContextVar at write time and sets `ip_address`/`user_agent` on the
  `AuditLog` row it builds. Outside a request (scheduler/purge jobs, direct
  dispatcher calls) the ContextVar is `None`, so both columns correctly write
  `NULL` for system-initiated changes — there is no request to attribute them
  to.
- **Layering stays clean**: domain events remain transport-free — they never
  carry IP/UA. `infrastructure → core` is a legal import direction; the
  enrichment happens entirely in the infrastructure-layer handler at the
  moment it builds the persistence row, not in the domain event itself. This
  keeps `AuditableEvent` reusable outside an HTTP context (already true for
  scheduler-driven audit writes) without a fake/null transport payload baked
  into the domain type.

### 3. Rate limiter covers `/api/v1/invitations` too
`RateLimitMiddleware.path_prefix: str` became `path_prefixes: tuple[str, ...]`
(default `("/api/v1/auth",)`; match is `any(path.startswith(p) for p in
prefixes)`). `main.py` now passes `("/api/v1/auth", "/api/v1/invitations")`.
Same limiter instance, same 20 req/min/IP bucket, same `Retry-After` +
`detail.retry_after` semantics — `POST /invitations/{token}/accept` (the
public, unauthenticated, token-bearing accept surface) is now covered.

**Admin invitation CRUD is deliberately NOT covered.** `POST/GET/DELETE
/api/v1/clans/{clan_id}/invitations[/…]` lives under a different path prefix
and requires an authenticated, approved admin — it is not the
unauthenticated-adjacent surface this rate limit is protecting. Extending the
limiter there would rate-limit legitimate admin workflows (e.g. bulk-inviting
a clan) for no abuse-surface benefit, since the authenticated-admin gate
already bounds who can call it.

### 4. `engine.dispose()` on shutdown
One-liner in `main.py`'s lifespan `finally` (after scheduler stop): the async
engine is disposed so pooled connections close cleanly on SIGTERM instead of
being dropped by the OS. Logged (not raised) on failure so a dispose error
never blocks the rest of teardown.

## Consequences
Easier: the clan-input branch oracle and the status-code-on-duplicate-email
oracle are both **structurally closed** — register can no longer be used to
enumerate accounts via clan-validation branching, nor via a dedicated
already-exists status code, and provider-unavailable (503) is symmetric on
both paths. Register joins forgot-password/resend-verification as
non-enumerating on every path reachable under Supabase's **default**
password policy. One residual is accepted, not eliminated: the
weak-password status divergence above is config-gated (see that section) —
it doesn't reopen under default settings, but tightening the deployed
Supabase project's password policy past our 8-char minimum could reopen a
narrow status/body oracle on that one branch. Audit rows are now forensically useful:
an investigator can answer "what IP/browser did this write come from"
instead of finding `NULL` on every row. The invitation-accept surface no
longer sits outside the abuse-mitigation net that every other public auth-
adjacent endpoint already has.

Harder: `POST /auth/register` is a breaking response-contract change — any
future frontend must be built against the new uniform shape from day one
(there is no dual-shape transition window). The residual timing side-channel
on register is an accepted, not eliminated, risk — revisit if the threat
model changes. `RequestMetaMiddleware` and `RateLimitMiddleware` now both
depend on `resolve_client_ip`'s proxy-trust assumption (exactly one trusted
appending proxy) — a topology change (e.g. multiple proxies) would need both
call sites updated together, not just the rate limiter's.

## Related
- [ADR-015](015-email-verification-flow.md) — established the
  non-enumerating pattern for resend-verification; register now joins it.
- [contracts/rest-auth-api.md](../contracts/rest-auth-api.md) — register
  response-shape change.
- [contracts/error-codes.md](../contracts/error-codes.md) — removal of
  `auth.email_already_exists`.
- [contracts/frontend-integration-guide.md](../contracts/frontend-integration-guide.md)
  — register → always check-email screen.
- [architecture/auth-flow.md](../architecture/auth-flow.md) — rate-limit
  scope, register non-enumeration paragraph.
- [architecture/api-design.md](../architecture/api-design.md) — auth route
  table + rate-limit scope note.
