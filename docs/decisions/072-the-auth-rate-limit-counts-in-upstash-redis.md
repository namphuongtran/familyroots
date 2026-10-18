# ADR-072: The Auth Rate Limit Counts in Upstash Redis, Shared by Every Instance

## Status

Accepted, shipped (2026-10-18). Resolves issue #257, "The auth rate limit is per instance on
Vercel". The database was provisioned by #281. Amends ADR-021 Decision 3 and ADR-065 § 7 by
dated amendment.

**This ADR ships with its code**, in the same pull request. Source readings were taken on
`main` at `0c69939` on 2026-10-18, before the change.

## Context

On Vercel Functions the backend runs as many short-lived instances (ADR-065).
`RateLimitMiddleware` kept its sliding-window log in process memory
(`backend/app/core/rate_limit.py:58` at `0c69939`, `self._hits: dict[str, list[float]]`), so the
auth budget of 20 requests per 60 seconds per IP (ADR-021 Decision 3) held **per instance**.
ADR-065 § 7 accepted that as a follow-up. It shows up in production. On 2026-10-11 at
11:57:56Z, after a 65-second quiet period, 40 concurrent `GET /api/v1/auth/me` from one address
to `https://familyroots-api.vercel.app` read `34 × 401, 6 × 429`. One shared bucket would have
read 20 and 20. `/auth/me` has not been counted since #280, so the reading after this change uses
`POST /api/v1/auth/login` with body `{}`, which is counted both before and after.

**The store exists.** #281 created an Upstash Redis database through the Vercel Marketplace,
read on 2026-10-18 with `vercel integration list --scope namtp`: resource
`familyroots-ratelimit`, product "Upstash for Redis", integration `upstash-kv`, connected to
`familyroots-api` only. The integration injected five variables into both **Production and
Development**, none into Preview: `KV_REST_API_URL`, `KV_REST_API_TOKEN`,
`KV_REST_API_READ_ONLY_TOKEN`, `KV_URL` and `REDIS_URL`. The region (`ap-southeast-1`, beside
Vercel's `sin1`) and the free plan were chosen in the dashboard; the CLI prints neither.

## Decision

### 1. The middleware counts through a store port, with two adapters

`RateLimitStore` (`backend/app/core/rate_limit.py`) has one operation:
`hit(key, *, max_requests, window_seconds, now) -> RateDecision`. It decides one request and
records it if admitted, as one atomic step. A refusal carries `retry_after`.

- **`InMemoryRateLimitStore`** is the old log, moved out of the middleware unchanged: prune on
  every hit, a global sweep once a window. It is one per instance.
- **`UpstashRateLimitStore`** (`backend/app/infrastructure/upstash_rate_limit_store.py`) is the
  shared one.

**The rules are today's, exactly.** The window is 60 seconds and slides, and a hit counts while
it is newer than `now - 60`. A refused request is not recorded. `retry_after` is the oldest
admitted hit's distance from the cutoff, truncated, plus one second. The `rate_limited` 429
envelope and its `Retry-After` header are unchanged, and the middleware still builds them
(`docs/contracts/error-codes.md` "429 and Retry-After" needs no edit). The key is the client IP,
resolved as before.

**The clock is now wall-clock time, `time.time()`, not `time.monotonic()`.** A shared store
compares hits that different processes recorded, and monotonic clocks have no common origin
across processes. What that gives up is small: if a host's clock steps backward, a hit recorded
before the step stays in the window longer by the size of the step.

### 2. Upstash holds an exact sliding log, checked and recorded in one Lua script

Each key is a sorted set whose members are hits, scored by their time. One `EVAL` per counted
request runs:

1. `ZREMRANGEBYSCORE key -inf <cutoff>`, which drops the hits that left the window. The
   in-memory store keeps `t > cutoff`, and this removes `t <= cutoff`, the same rule.
2. If `ZCARD` is at the budget, return the oldest score. Nothing is recorded.
3. Otherwise `ZADD` the hit, with a member unique to it, and `PEXPIRE` the key for the window.

Redis runs a script without interleaving another command, so two instances deciding at the same
moment cannot both take the last slot. The expiry is renewed on every admitted hit, so an idle IP
costs nothing after a minute. Scores travel as strings both ways, so Lua never formats a float.

**The key is `familyroots:<APP_ENV>:rate-limit:auth:<ip>`.** The integration connected one
database to both Production and Development, and `APP_ENV` keeps their counts apart.

**It talks to Upstash over the REST API, one HTTPS `POST` per decision**, with `httpx2`, which the
backend already uses. A frozen instance holds no Redis connection to go stale, and the call needs
no new dependency. One client is kept per event loop, so a burst reuses its connection.

### 3. A failing store falls back to the instance's in-memory bucket, never to a 5xx

Any exception from the call, a non-200, an `error` body, an unreadable body, or no answer within
**0.5 seconds** raises `RateLimitStoreUnavailableError`. The catch is broad on purpose: whatever
escapes the adapter answers sign-in with a 500. The middleware then decides the request with its own
`InMemoryRateLimitStore`, which is what every instance did before this change.

**Why 0.5 seconds.** Upstash answers an `EVAL` in a few milliseconds from the same region, and a
cold instance's first call adds a TLS handshake. Half a second is many times both. It is also the
most a sign-in waits when the store is down. The deadline is one `asyncio.timeout` around the
whole call, connection included, because `httpx2` would time each phase separately.

**Every fallback logs a warning. Sentry gets one warning per instance per 60 seconds.** An outage
fails every counted request, and one Sentry event each would spend the project's quota on a
single fact.

The fallback bucket counts only what the instance decided while the store was failing. It is not
written while the store answers.

### 4. Production refuses to boot without the store

`Settings` gains `KV_REST_API_URL` and `KV_REST_API_TOKEN`, the names #281's integration
injected. The pair is used and the read-only token, `KV_URL` and `REDIS_URL` are not.

- **Both set** selects the Upstash store, in any environment.
- **Neither set** selects the in-memory store, and **production refuses to boot**, in the style of
  the `RATE_LIMIT_TRUST_FORWARDED_FOR` refusal. Development, tests and the authenticated e2e
  harness set neither.
- **One without the other is refused in every environment**, because it would quietly select the
  in-memory store. The error names the missing half.

`create_app(rate_limit_store=...)` takes a store in place of the one settings select. Two apps
given one store stand for two Vercel instances, which is how the test below reads the shared
count.

**The image e2e job boots the backend under `APP_ENV=production`**, so it now needs the pair.
`docker-compose.yml` gains `redis` and `redis-http`, a Redis behind
`hiett/serverless-redis-http:0.0.10`, which answers Upstash's REST API. The job's `api.env`
points `KV_REST_API_URL` at `http://redis-http` with that emulator's own token. That job's
backend therefore counts through the production adapter.

## Consequences

- **The budget holds across instances.** A burst from one address is refused at 20 whichever
  instance serves each request.
- **Upstash joins the sign-in path, but cannot fail it.** When the store is down, the limit is
  what it was before this change, 20 per instance, and Sentry says so.
- **Every counted request pays one round trip** to Upstash in the same region, at most 0.5 s. No
  other route is affected. Only the seven counted routes call the store (ADR-021, amended by
  #280).
- **The production variables are already in place.** #281's integration set the pair in
  Production, so a release of this change boots. A project whose integration is removed fails
  every cold start with the refusal of § 4, by design.
- **The tokens are readable in the Vercel dashboard.** The integration created all five
  variables as type `Config`, not `Secret`. Vercel does not allow sensitive variables in
  Development.
- **`MetricsFailureThrottle` stays per instance**, as ADR-065 § 7 accepted. Metrics stay off on
  Vercel, so nothing reaches it there.
- **A developer whose `backend/.env` holds the Development pair counts in the hosted database**,
  under `APP_ENV`'s prefix. Leave the pair out of a local `.env` unless that is the point.

## Alternatives considered

- **The Vercel Firewall's rate-limit rule.** It answers before FastAPI runs, so its 429 carries no
  `rate_limited` envelope and no CORS headers, which breaks `docs/contracts/error-codes.md`. On
  Hobby it allows one rule per project, a fixed window only, keyed by IP or JA4 digest (Vercel
  docs, "WAF Rate Limiting", last updated 2026-08-28, read 2026-10-11). Rejected in #257's triage.
- **Postgres.** Every counted request, refused ones included, would open a pooler connection,
  because the engine pools nothing behind Supavisor (ADR-065 § 2). A burst would then spend the
  pooler's clients for every route. Rejected in #257's triage.
- **A fixed-window counter (`INCR` with `EXPIRE`).** One command cheaper, but it admits up to
  twice the budget across a window boundary. That changes the rules, which #257 kept.
- **The `upstash-redis` or `upstash-ratelimit` SDKs.** A dependency for one call, and
  `upstash-ratelimit`'s sliding window is an approximation of two fixed windows, not today's exact
  log.
- **Redis over TCP (`REDIS_URL`).** A connection per instance that a frozen instance would hold
  open, for no gain over one HTTPS request.

## Verification

- **Gate:** the backend full quality gate.
- **`backend/tests/integration/test_rate_limit_shared_store.py`**, against the emulator.
  - Two `create_app()` instances on one `UpstashRateLimitStore` split 40 concurrent
    `POST /api/v1/auth/login` with body `{}`. They read `20 × 422, 20 × 429`, and the 429 carries
    the envelope and a matching `Retry-After`.
  - The same reading with no store handed in: each app selects the adapter from its settings.
  - **Negative control:** two `InMemoryRateLimitStore` read `40 × 422`.
  - The adapter alone, request by request: the 21st is refused with `retry_after` 41, and a
    refusal is not recorded.
- **`backend/tests/unit/test_rate_limit_store_fallback.py`.** Six failures of the store (a
  refused connection, a wrong token, a script error, a body that is not JSON, JSON of another
  shape, and a URL `httpx2` cannot parse) each read `20 × 422` then `429`, with one Sentry
  warning. A socket that never answers is abandoned at the deadline.
- **`backend/tests/unit/test_config_validation.py`.** Production without either half refuses to
  boot, and half a pair is refused in development.
- **Negative controls, planted on 2026-10-18 and each seen to fail:**
  - The middleware ignoring the store it was given: `40 × 422`.
  - `create_app` ignoring the settings: the settings case reads `40 × 422`.
  - The Lua script recording before it checks: two shared-store cases fail.
  - The store error escaping the fallback: every fallback case fails.
  - A fallback that admits everything: the 21st reads 422.
  - A Sentry warning for every failure: every fallback case fails.
  - No deadline: the never-answering case times out.
  - The adapter catching only `httpx2.HTTPError` and parse errors: the unparsable URL, whose
    `InvalidURL` is not an `HTTPError`, fails its case.
  - The production refusal removed: both production cases fail.
- **Owed, in production.** Before the release and again after it, send 40 concurrent
  `POST /api/v1/auth/login` with body `{}` to `https://familyroots-api.vercel.app` after a
  65-second quiet period, and count the codes. Before is expected to admit more than 20. After is
  expected to read `20 × 422, 20 × 429`. Both readings go on #257.

## Related

- [ADR-021](021-non-enumerating-auth-surfaces.md) Decision 3: the budget, the counted routes and
  the 429. Amended by this ADR.
- [ADR-065](065-the-backend-runs-on-vercel-functions.md) § 7: the per-instance count, accepted
  then. Amended by this ADR for the auth limiter only.
- [ADR-040](040-metrics-token-floor-and-throttle.md): `MetricsFailureThrottle`, which stays per instance.
- Issues #257 (this change), #281 (the database) and #280 (the counted routes).
