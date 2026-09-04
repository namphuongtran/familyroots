# ADR-056: `NEXT_PUBLIC_API_URL` Splits Into a Browser Variable and a Server Variable

## Status

Accepted (2026-08-22). It was opened by the Supabase-variable fix while that change fixed the two
Supabase build-time variables and correctly declined to fix this one in the same change, because
unlike those two it has no single correct value.

Every measurement below was taken on **2026-08-22** in
`.claude/worktrees/web`, from commit `3db8f96` (branch `seed/s-076-adr-056-api-url`). Docker
29.7.2, Compose v5.4.0, `node:22-alpine`, Next.js 16 (`output: 'standalone'`).

## Context

### The mechanism, established by that fix and re-verified here rather than re-derived

`NEXT_PUBLIC_*` inlining in Next.js is **not scoped to Client Components**. It is a build-time
text substitution across the whole bundler graph: every static reference to
`process.env.NEXT_PUBLIC_X` anywhere the bundler can see it — a Client Component, a Server
Component, middleware, a route handler — is replaced with the literal value `process.env.X` held
**at `pnpm build` time**, and a value passed only through `environment:`/`docker run -e` at
container start never reaches it. This was proved for `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` with a two-run probe: one image built with both as empty build
arguments, run twice with two different runtime values on the same names, both runs read back the
empty build-time value. `web/Dockerfile`'s own comment on `ARG NEXT_PUBLIC_SUPABASE_URL` (added by
that fix) carries the account.

### `NEXT_PUBLIC_API_URL` has the identical exposure, and a second, harder problem on top of it

`web/src/lib/api/axios.ts:6` reads it as the shared Axios client's `baseURL`:

```ts
const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1',
  ...
```

`web/CLAUDE.md`'s own "Migration notes" section, cited at source: `axios.ts` is not one slice's
transport, it is "one file shared by every slice" — `grep -rln "lib/api/axios\|from 'axios'" src`
(2026-08-22) finds it imported by `src/lib/hooks/useMembers.ts` (a `'use client'` file, confirmed
by its own `'use client'` directive at line 1) and by `src/lib/api/{documents,events,members,
relationships,tree}.ts` and `src/infrastructure/admin/http-admin-repositories.ts` in turn. So this
value is inlined into the browser bundle the same way the two Supabase variables were.

`web/src/lib/server/auth-context.ts:20-21` (before this change) read the **same** variable,
server-side, for a genuinely server-to-server call:

```ts
function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
}
```

used at `:44` to fetch `${getApiBaseUrl()}/me/clans` from inside `getServerAuthContext()`. Per the
mechanism above, this reference is inlined too — it is not exempt for being server code.

**The two callers need different values, which is the reason this is a decision and not a second
instance of that fix.** Inside `docker-compose.yml`, `auth-context.ts`'s fetch runs _inside the
`web` container_, on the `familyroots` bridge network, where the backend is reachable only at the
compose-network hostname `http://api:8000/api/v1` — `localhost` from inside that container means
the `web` container itself. A browser on the host has no route to that hostname at all: Docker's
embedded DNS resolves compose service names only for other containers on the same network, never
for the host's own resolver. **One literal baked at build time cannot be both values**, which is
exactly what the pre-existing `docker-compose.yml` comment (written by that fix while declining to fix
this) already said, and what the paragraph below confirms with a real browser rather than reasoning
about DNS in the abstract.

### Control 1 — the mechanism, generalised: one prefix is baked, the other is live

Built one image from this seed's `web/Dockerfile` (which now declares
`ARG NEXT_PUBLIC_API_URL`) with:

```
docker build -t familyroots-web-s076-test \
  --build-arg NEXT_PUBLIC_SUPABASE_URL= \
  --build-arg NEXT_PUBLIC_SUPABASE_ANON_KEY= \
  --build-arg NEXT_PUBLIC_API_URL=http://BAKED-BROWSER-VALUE.invalid:8000/api/v1 \
  ./web
```

Ran it **twice**, sharing the image, each run passing **different** runtime values on **both**
names, through two temporary probes reverted before this seed's commit (`git diff --stat` on the
final commit carries no `debug-probe` file — see "What is not in this diff" below):

| Run | `-e NEXT_PUBLIC_API_URL=`                       | `-e API_URL=`                                 |
| --- | ----------------------------------------------- | --------------------------------------------- |
| 1   | `http://RUNTIME-OVERRIDE-1.invalid:9999/api/v1` | `http://server-value-ONE.invalid:7000/api/v1` |
| 2   | `http://RUNTIME-OVERRIDE-2.invalid:9999/api/v1` | `http://server-value-TWO.invalid:7000/api/v1` |

`curl localhost:<port>/api/debug-probe-s076` (a temporary Route Handler reading both env vars
live, server-side) on each run:

- Run 1: `{"NEXT_PUBLIC_API_URL":"http://BAKED-BROWSER-VALUE.invalid:8000/api/v1","API_URL":"http://server-value-ONE.invalid:7000/api/v1"}`
- Run 2: `{"NEXT_PUBLIC_API_URL":"http://BAKED-BROWSER-VALUE.invalid:8000/api/v1","API_URL":"http://server-value-TWO.invalid:7000/api/v1"}`

**Two different readings for `API_URL`, matching each run's own runtime value — the split does
what it is supposed to.** **The same, frozen reading for `NEXT_PUBLIC_API_URL` on both runs,
ignoring the runtime override entirely — confirming, in a server-side code path this time rather
than only middleware and the callback route, that the finding generalises to this variable.**
The failing-would-look-like case (both readings equal to `RUNTIME-OVERRIDE-*`, meaning the prefix
was not actually inlined and the split bought nothing) did not occur.

### Control 2 — the browser, per the seed's own instruction to confirm this before building on it

Navigated Playwright-driven Chromium to `http://localhost:<port>/vi/debug-api-probe-s076`, a
temporary Client Component that calls `api.get('/__s076_probe__')` on mount — the same `axios.ts`
instance every legacy hook shares — on both Control 1 runs, and read the outgoing request from the
page's own Network activity:

- Run 1: request URL `http://baked-browser-value.invalid:8000/api/v1/__s076_probe__`
- Run 2: request URL `http://baked-browser-value.invalid:8000/api/v1/__s076_probe__`

(lower-cased by Chromium's own URL parser, per the URL spec's host-lowercasing rule — the same
build-time value as Control 1's server reading, case aside.) **Identical on both runs, and
identical to the build-time value, never the per-run `RUNTIME-OVERRIDE-*` override.** This is the browser-side confirmation Control 1's server probe
already implied: the client bundle's `baseURL` is fixed at `pnpm build`, and no runtime
environment variable — passed under either name — reaches it.

**The specific claim the seed asked to confirm in a browser** — "a browser cannot reach the
compose-network hostname" — was checked directly in that same live Chromium page, by running
`fetch()` against both candidate targets from the page's own JavaScript context
(`browser_run_code_unsafe`, `page.evaluate(u => fetch(u), url)`) and reading each attempt back off
the page's Network activity, which reports the browser's real per-request failure code where a
thrown `TypeError: Failed to fetch` in JavaScript itself does not distinguish the cause:

| Target fetched, live, from the browser                                                                                          | Network panel's reading       |
| ------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| `http://api:8000/api/v1/__s076_probe__` (the compose-network hostname `docker-compose.yml` baked by default before this change) | `net::ERR_NAME_NOT_RESOLVED`  |
| `http://localhost:8000/api/v1/__s076_probe__` (the browser-facing default this ADR moves the default to)                        | `net::ERR_CONNECTION_REFUSED` |

**Two different failure codes for two different targets, from one running page, in the browser
that would actually load this app.** `ERR_NAME_NOT_RESOLVED` means Chromium never got as far as
attempting a connection — its own resolver has no address for `api`, because that name means
something only to Docker's embedded DNS, seen only by other containers on the `familyroots`
network. `ERR_CONNECTION_REFUSED` means the name resolved to `127.0.0.1`/`::1` and Chromium tried
and failed to open a socket there — proof the _name_ was fine and nothing was listening on that
port on the host at the time of the probe (no `api` container was published to port 8000 during
this measurement). This is the pass/fail contrast the seed asked for, not a token reading that
would pass either way (`.claude/rules/testing.md`, "A test pins an outcome, not a setting").

### What this control does not prove, stated plainly

**A green gate is not evidence here**, per the seed's own instruction: no test in the suite
compiles a Docker image or reads what a browser actually receives, so the whole of the mechanism
above is established by a hand-run probe, not a suite assertion, and stays unverified by
`pnpm test:unit`/`test:component`/`test:e2e`/`build` after this change lands. Nothing added by this
seed changes that — see "What this ADR deliberately does not decide".

## Decision

**`NEXT_PUBLIC_API_URL` and `API_URL` are two different environment variables, one baked at build
time for the browser, one read live at request time for the server.**

- **`NEXT_PUBLIC_API_URL`** keeps its name and its one reader, `web/src/lib/api/axios.ts`. It
  carries the **browser-facing** origin only — a URL the browser itself can resolve and reach.
  Baked into the image at `docker compose build web` / `pnpm build` time, exactly as today,
  because a client bundle has no other way to receive a value.
- **`API_URL`** is new, carries no `NEXT_PUBLIC_` prefix, and is read by
  `web/src/lib/server/auth-context.ts`'s `getApiBaseUrl()` alone. It carries the
  **server-to-server** origin, read live via `process.env.API_URL` on every call, with no `ARG` in
  `web/Dockerfile` and no build-time promotion — the whole reason a second variable is worth having
  is that this one is _not_ baked, so it can differ from `NEXT_PUBLIC_API_URL` without a rebuild,
  and can be corrected in a running container by changing `docker-compose.yml`'s `environment:`
  (or a platform's runtime env panel) alone.
- **`getApiBaseUrl()` reads `API_URL` first, `NEXT_PUBLIC_API_URL` second, and the existing
  `http://localhost:8000/api/v1` literal last**, so a deployment shape that only sets one public
  origin (Vercel, see below) needs no second variable at all — the fallback makes the split opt-in
  per deployment shape rather than a second required variable everywhere.

### What this costs, per deployment shape

**Vercel — how the web app actually ships (`.github/workflows/web-ci.yml:209`, `vercel deploy
--prod`; no Docker image is built or shipped for `web/` today).** Zero required cost. Vercel has no
internal compose-style network: `auth-context.ts`'s request and the browser's request both cross
the same public internet to reach the backend's one real, public origin, so `API_URL` can be left
unset and `getApiBaseUrl()`'s fallback to `NEXT_PUBLIC_API_URL` is already correct. Setting `API_URL`
to the same value as `NEXT_PUBLIC_API_URL` in the Vercel dashboard is allowed and changes nothing;
it is not required. Vercel already builds `NEXT_PUBLIC_*` per environment (Production / Preview /
Development), so nothing about how the browser value is supplied changes at all.

**Compose (local dev, `docker-compose.yml`).** `web/Dockerfile` gains one more `ARG`/`ENV` pair,
mirroring the two already added — this change's whole code diff in that file. `docker-compose.yml`'s
`web.build.args` gains `NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000/api/v1}`
(the browser-facing default, changed from the compose-hostname default flagged as wrong), and
`web.environment` gains `API_URL: ${API_URL:-http://api:8000/api/v1}` (the compose-network default,
genuinely live because it carries no prefix). **The image stays environment-specific for the
browser half**, exactly as documented for the two Supabase variables — an image built
for one environment's public backend origin cannot be promoted to a different one unchanged — and
this seed adds nothing new to that cost, since `NEXT_PUBLIC_API_URL` was already going to need a
rebuild per environment the moment it held a real value instead of the empty string it was left
at.

**A future container deploy on a shared network (ECS, Kubernetes, or similar).** Same split,
applied at that platform's own boundary: bake a public load-balancer hostname into
`NEXT_PUBLIC_API_URL` at build time (one image per environment, as compose already requires), and
supply the cluster-internal service DNS name as `API_URL` through that platform's ordinary runtime
environment configuration — no rebuild needed to change it, since `API_URL` is never baked. Nothing
about this decision assumes compose specifically; the split is general to any shape with a private
network the browser cannot reach.

## Alternatives considered

| Alternative                                                                                                                                                                                         | What it would have cost                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A same-origin path, proxied through Next.js** (the browser always calls a relative path such as `/api/v1/...`, and Next.js forwards server-side to the real backend using a server-only variable) | Would remove the two-value problem entirely — there would be exactly one real caller of the backend origin, the Next.js server, on every deployment shape. Rejected on an existing, explicit rule rather than on the merits of the idea: `.claude/rules/nextjs.md` § 4, "Do not add a route handler to proxy or re-wrap a backend endpoint. Call the backend through `apiFetch` instead" — written before this seed and binding on new code in `web/`. A `next.config.ts` rewrite is not literally a route handler, but it is the same shape the rule exists to forbid: an added indirection between the browser and the real API that this codebase has already decided against once. Overriding a standing rule to solve one variable is a larger, separate decision than this seed is sized for |
| **Fetch the API origin at runtime from a Server Component and stop treating it as `NEXT_PUBLIC_*` at all**                                                                                          | Removes the build-time bake for the browser too, but trades it for a real cost on every page load: `axios.ts` sets `baseURL` at module-evaluation time, synchronously, so the browser would need to block its first request on a config fetch (or accept a race where early requests use a wrong default). It does not remove the underlying two-origin problem either — the browser would still need _some_ runtime-supplied, host-reachable value, fetched over a new endpoint that itself has to be reachable before it can say where anything else is. More moving parts than the two-variable split, for a problem the split already resolves                                                                                                                                                 |
| **Bake `http://api:8000/api/v1` as the one value, keep the compose default as-is, and tell the browser to reach the API through a different host mapping instead**                                  | This is what `docker-compose.yml` did before this seed, and Control 2 shows it directly: the browser gets `net::ERR_NAME_NOT_RESOLVED`, not a slower path, a hard failure. Fixing it by changing what `api` resolves to on the host (an `/etc/hosts` entry, a second published hostname) pushes an operational step onto every developer's machine for a problem the app's own two-variable split solves in the repo instead                                                                                                                                                                                                                                                                                                                                                                       |
| **One variable, always the browser-facing value, and let `auth-context.ts` also point at the browser-facing origin inside compose** | Works only where the backend's published host port is reachable from _inside_ the `web` container too — true today on a Linux Docker host reaching `localhost` back to itself only via `host-gateway` tricks already in use elsewhere in this file for Supabase (`extra_hosts`), false in general, and needlessly round-trips a same-network call out to the host's port mapping and back in in the cases where it does work. Kept `API_URL` as the real compose-network hostname instead, which is what `docker-compose.yml` already did for `SUPABASE_URL` in the `api` service |

## Consequences

### What this buys

- **The browser can actually reach the backend from a compose deployment.** Before this change,
  `docker-compose.yml`'s literal default baked the compose-network hostname into the browser
  bundle, which Control 2 shows fails outright with `net::ERR_NAME_NOT_RESOLVED`. That was a real,
  live defect in local dev, not only a naming inconsistency.
- **The server-to-server call keeps working from inside the `web` container**, and can now be
  changed — corrected, pointed at a different backend, moved to a different network — by editing
  `docker-compose.yml`'s `environment:` (or a platform's runtime env panel) alone, with no image
  rebuild, because `API_URL` is never baked.
- **Vercel, the shape that actually ships this app, needed no new required configuration.** The
  fallback chain means the split is available where a deployment shape needs it and invisible where
  it does not.

### What this does not buy, stated plainly

- **It does not remove the underlying bake.** `NEXT_PUBLIC_API_URL` is still inlined at build time,
  with everything that implies: a running container cannot pick up a new browser-facing origin
 without a rebuild, exactly as the two Supabase variables already cannot.
- **It does not add a test.** Per the "What this control does not prove" section above, nothing in
  `pnpm test:unit`/`test:component`/`test:e2e`/`build` asserts what a browser bundle was built
  with, before or after this change. A future defect in this area — for example, a compose default
  reverting to the wrong hostname — would pass every gate command and only be caught by a hand-run
  probe like the one in "Context" above, or in a real deployment. Building that gate (compiling an
  image and reading a served bundle's baked value, in CI) is not attempted here; it is a
  meaningfully larger undertaking than a two-variable split and is not named as owed by this ADR,
  since no seed has asked for it yet.
- **It does not touch `NEXT_PUBLIC_SUPABASE_URL` or `NEXT_PUBLIC_SUPABASE_ANON_KEY`.** Both hold
  one correct value for every caller already, so neither needs a second,
  non-public variable.
- **It does not revisit `.claude/rules/nextjs.md` § 4's proxy rule.** The rule stands; see
  "Alternatives considered" for why this decision does not need to challenge it.

## What this ADR deliberately does not decide

- **Whether a future gate should compile an image and read the browser bundle's baked value.**
  Named above as a real gap this decision does not close, not decided here.
- **`NEXT_PUBLIC_API_ORIGIN`**, a third variable documented in `web/.env.example` and
  `web/CLAUDE.md`'s own "Env vars in `.env.local`" line. `grep -rn "NEXT_PUBLIC_API_ORIGIN" web/src`
  (2026-08-22) returns no match in `web/src` at all — it is read nowhere. Out of scope: this seed's
  sources name `NEXT_PUBLIC_API_URL` only, and a dead variable with no reader is not the defect this
  ADR exists to fix.
- **Any change to the backend's CORS configuration.** `backend/` is out of scope per this seed's
  fences; this decision assumes whatever CORS posture already lets the browser reach the backend's
  public origin today continues to.

## What is not in this diff

Two files existed only for Control 1 and Control 2 above and are not part of this seed's commit:
`web/src/app/api/debug-probe-s076/route.ts` and
`web/src/app/[locale]/debug-api-probe-s076/page.tsx`. Both were created, built into the test image,
read from, and deleted before committing — the same "throwaway... not in this diff" pattern
`web/Dockerfile`'s own comment already uses for its console.error probes.

## Related

- The Supabase-variable fix in the same file, which found this problem while fixing the two
  variables and opened this seed rather than fixing it in the same change — see its own dated
  correction for the mechanism this ADR builds on.
- `web/Dockerfile` and `docker-compose.yml`'s `web` service — the comments there, and this
  seed's additions beside them.
- `.claude/rules/nextjs.md` § 4 — the standing rule the "same-origin proxy" alternative would have
  had to override.
