# ADR-040: `METRICS_TOKEN` — Length Floor at Boot, and a 404-Preserving Failure Throttle

## Status
Accepted, shipped (2026-08-03). Closes work-register §3.1.

## Context
`GET /internal/metrics` (ADR-033) serves Prometheus RED metrics behind a static
`X-Metrics-Token` header. It is off by default (`METRICS_ENABLED=false`) and every
failure path answers **404, never 401/403**, so an unauthenticated scan cannot
confirm the endpoint exists (ADR-021). Two gaps were recorded as knowingly
unfixed in `docs/ops/monitoring.md` and work-register §3.1:

1. **No floor on the configured token.** Settings validation rejected only an
   *empty* `METRICS_TOKEN` while `METRICS_ENABLED` was true. A one-character
   token booted and served. The docs said "use `openssl rand -hex 32`", but
   convention is not enforcement, and the thing being protected — route names,
   request volumes, latency distributions, the full shape of the API's traffic —
   is exactly the reconnaissance an attacker wants before touching auth.
2. **No rate limit and no trace.** A failed attempt was a silent 404 outside
   `RateLimitMiddleware` (which only covers `/api/v1/auth` and
   `/api/v1/invitations`). The endpoint could be brute-forced at full request
   rate, and nothing anywhere recorded that it had happened.

The hard part is (2): the obvious response to over-limit traffic is `429`, and a
`429` on this path is *itself* an enumeration signal. It is a worse one than the
`401` this endpoint already refuses to send, because no nonexistent path ever
returns `429` — it confirms both that `/internal/metrics` exists and that it is
considered worth guarding, which tells the attacker they found something real.

## Decision

### 1. A length floor, enforced at boot — and again at request time

`metrics_token_weakness(token)` (`app/core/config.py`) returns why a token is
unusable, or `None`. It requires **at least 32 characters** and **at least 8
distinct characters**.

**It is a length floor, not an entropy floor, and is documented as one.** Entropy
is a property of how a string was *generated*; nothing that inspects the finished
string can observe that. 32 characters of `openssl rand -hex 32` output carries
128 bits — the conventional floor for a secret an online attacker may guess at.
32 characters of `"abcdabcdabcd…"` carries about four bits, and passes. The
guarantee is therefore narrow and worth stating exactly: **a token produced by
the documented random generator clears the floor, and a hand-typed one almost
never does.** Nothing stronger is claimed.

The distinct-character minimum exists because the one genuinely worthless shape a
pure length check waves through is padded repetition (`"a" * 64`, `"0" * 32`),
which is also the likeliest lazy value. It is not an entropy measurement either:
`"abcdefgh"` repeated four times passes. It is a cheap guard on the degenerate
end, and calling it anything more would be false comfort.

Rejected: a Shannon-entropy estimate over the string. Over a 32-character sample
it is a bad estimator, and the number it produces would invite exactly the
overconfidence this section is written to avoid. Rejected: making the floor
configurable — a security floor an operator can lower is a floor that gets
lowered under deploy pressure.

**Enforced at boot (primary).** The check lives in `Settings`'
`_enforce_production_safety` validator, beside the existing empty-token check,
and fires in **every** environment rather than production only — the pair is
opt-in, so nothing reaches the branch unless someone deliberately set
`METRICS_ENABLED=true`, and a dev `.env` that normalises a weak token is a `.env`
that gets copied.

Failing startup was chosen over a runtime-only check. The stated risk — that
failing validation takes down a running deployment on a config reload — **does
not exist in this codebase**: settings are read exactly once per process
(`@lru_cache` on `get_settings`, no SIGHUP handler, no watcher, no reload path),
so the only way a new value is ever read is a fresh process, i.e. a deploy. On
Render a failed boot means the deploy fails and the previous release keeps
serving — the same posture `main.py`'s lifespan already takes for an unmigrated
database and for a non-engaging RLS role. If a reload path is ever added, this
decision needs revisiting *with* it; today, refusing to boot costs a failed
deploy and buys never silently serving a guessable endpoint.

**Re-checked at request time (backstop).** The handler calls
`metrics_token_weakness` again and 404s if it fails. The route must not depend on
validation having run: a `monkeypatch`, a directly-constructed `Settings`, or a
future config path can all bypass it, and the existing test
`test_enabled_with_an_empty_token_setting_is_404` already encodes that principle
for the empty case. A bypassed gate degrades to *endpoint invisible*, never to
*endpoint guessable*. The misconfiguration is logged at `error` **once per app**,
because a silent 404 is indistinguishable from "switched off" to whoever is
debugging the scrape, and logging per probe would hand a scanner unbounded log
volume.

### 2. The throttle produces no response of its own — the 404 is unchanged

`MetricsFailureThrottle` (`app/core/metrics_guard.py`) is a per-IP sliding-window
counter of **failed** attempts: **5 per 60 seconds**, consulted by the handler.
Over budget, the handler raises the *same bare 404* it already raised — same
status, same envelope body, no `Retry-After`, no distinguishing header. It is
byte-identical to the framework's 404 for a path that does not exist (both become
`StarletteHTTPException(404, "Not Found")` through the one exception handler), and
that identity is asserted, not assumed
(`test_a_throttled_response_is_identical_to_a_nonexistent_path`).

**This is the answer to "how does rate limiting compose with ADR-021": it does not
compose, it hides.** A rate limit does not need a status code to work. Its whole
job is to stop the attacker making progress, and "your guesses are no longer
evaluated" achieves that completely while telling them nothing. The `429` would
be a courtesy to a well-behaved client, and on an endpoint whose only legitimate
client holds the token and is never throttled, there is no well-behaved client to
be courteous to. So the non-enumeration property is not traded at all — the trade
the prompt anticipated turned out to be avoidable, which is why it was avoided.

Three properties make that work:

- **Only failures are counted.** A correct token is the scraper's normal
  behaviour every 15 seconds forever; counting successes would mean enabling
  metrics throttles the monitoring it exists to serve.
- **The budget is checked *before* the comparison.** Evaluating the guess and
  merely withholding the body would leave the guessing unlimited, which is the
  thing being limited. Pinned by
  `test_failed_attempts_are_throttled_and_stop_being_evaluated`, which burns the
  budget with wrong guesses and then requires that the **correct** token also
  404s — the only form of the test that means anything.
- **A disabled endpoint records nothing.** Metrics is off by default and this
  path takes internet background noise; counting it would let anyone grow the
  failure table on an endpoint with no secret to guess.

Consequence, stated plainly: a correct token presented while that client IP is
over budget is refused for the rest of the window. Since successes never
accumulate, the scraper's own budget is always empty, so this requires an
attacker **originating from the scraper's resolved client IP**. With
`RATE_LIMIT_TRUST_FORWARDED_FOR=true` that resolved address is the rightmost
`X-Forwarded-For` entry — the one our single trusted proxy appended, not a
caller-supplied one (`resolve_client_ip`, ADR-021) — so it cannot be spoofed into
the scraper's identity. Rightmost-wins matters more here than at any other call
site: a spoofable left-hand entry would both hand the attacker a fresh budget per
guess and let them blind an operator's monitoring.

5/min is far tighter than the auth limiter's 20/min because nothing legitimate
probes this path: a scraper holding the token is unaffected, and a *mis*configured
scraper polling every 15 seconds produces 4/min, stays under the limit, and logs
every rejection — which is the signal an operator wants.

### 3. Failed attempts now leave a trace, bounded by construction

Each counted failure logs one `warning` with the client IP, the running count and
the window. Volume is capped at 5 lines per IP per window because the exhaustion
check returns *before* the log line — so the logging cannot be amplified into a
cost attack. **The attempted token is never logged**: a near-miss in a log file is
a credential leak.

### 4. A separate throttle, not the auth `RateLimitMiddleware`

Reusing the auth limiter was rejected. Its response *is* the `429` + error
envelope that must not appear here; it counts every request rather than every
failure; and ADR-021 deliberately puts auth and invitations in one shared bucket,
so auth traffic could starve the scraper. It is also middleware, and only the
handler knows whether an attempt failed — a middleware inspecting a 404 cannot
distinguish a wrong token from a genuinely unknown path.

The new throttle is a plain class taking a header getter and a peer address
rather than a `Request`, so the window, the eviction and the proxy-trust rule are
unit-testable without an ASGI stack. It shares `resolve_client_ip` with the auth
limiter and the audit middleware, so IP resolution stays one implementation.

**Accepted duplication.** The sliding-window prune + periodic-sweep logic now
exists twice: `RateLimitMiddleware._prune`/`_maybe_sweep` and
`MetricsFailureThrottle._prune`/`_maybe_sweep`. ADR-021 explicitly extracted
`resolve_client_ip` to stop exactly this kind of copy drifting, so this is a debt,
recorded here rather than glossed. It was taken deliberately: unifying them means
refactoring the auth rate limiter — security-critical code with its own tests —
inside a change about metrics, trading a hardening win for the risk of an auth
regression. The right shape is a shared `SlidingWindowCounter` primitive that both
sit on, as its own change.

### 5. No new middleware

Everything lives in the route handler and one helper class. The documented
middleware order (asserted by
`test_documented_middleware_order_matches_reality`) is untouched — a fourth
ordering-sensitive layer added for one endpoint would be a poor trade.

## Consequences

Easier: `METRICS_TOKEN` can no longer be a one-character string, and the failure
is a failed deploy with an actionable message naming the setting and
`openssl rand -hex 32`, not a quietly guessable endpoint. Brute-forcing is capped
at 5 guesses/min/IP and leaves a bounded, greppable trail where it previously
left none. ADR-021's non-enumeration property is fully preserved and now
regression-tested against response *identity* — status, body and headers — not
just the status code.

Harder / accepted:

- The floor is a **length** floor. `"abcdefgh" * 4` passes and carries almost no
  entropy. Closing that would mean guessing at how the operator generated the
  value, which cannot be done from the string. The mitigation is documentation
  plus the generator command in the error message.
- **The throttle is per-process, in-memory.** With N replicas the effective limit
  is 5×N failures per window. Same trade the auth limiter already makes; Redis is
  the fix if it ever needs to be exact.
- An attacker originating from the scraper's own resolved client IP can blind the
  scrape for up to one window (see §2). Unspoofable behind a trusted proxy;
  accepted for a directly-exposed deployment, where `X-Forwarded-For` is not
  trusted and the resolved address is the real socket peer.
- Any deployment that had `METRICS_ENABLED=true` with a short token will now
  **fail to boot**. Nothing currently ships that way — `render.yaml` does not
  wire either variable and the endpoint 404s in production today — so the
  migration cost is zero at the time of writing.
- The window/sweep duplication in §4 is real debt with a named fix.

## Related
- [ADR-021](021-non-enumerating-auth-surfaces.md) — the non-enumeration rule this
  must not weaken, the shared `resolve_client_ip`, and the auth rate limiter whose
  `429` semantics are deliberately *not* reused here.
- [ADR-033](033-w3c-trace-context-sentry.md) — introduced `/internal/metrics`,
  `METRICS_ENABLED` / `METRICS_TOKEN`, and the 404-on-every-failure handler.
- [ops/monitoring.md](../ops/monitoring.md) — operator-facing token requirements,
  the throttle's behaviour, and how to read a 404 while scraping.
