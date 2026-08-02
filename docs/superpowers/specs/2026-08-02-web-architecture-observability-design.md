# Web architecture restructure + observability — design

**Date:** 2026-08-02
**Status:** approved (design), pending implementation plan
**Scope:** sub-project **A** of the frontend programme (see §1.2)

## 1. Context

### 1.1 Why now

The backend is production-ready: frozen REST contracts (`docs/contracts/*`), 33 ADRs,
a real-Postgres test harness, RLS defence-in-depth, structured JSON logging. The web
client was scaffolded **before** the contracts were frozen and has drifted:

| Observation | Evidence |
|---|---|
| Hexagon is decorative | `src/infrastructure/persons/person-command-repository.ts` is a one-line wrapper over `@/lib/api/members`; no DTO mapping, no real boundary |
| `domain/` is nearly empty | `src/domain/` holds only `shared/types.ts` (6 lines); the real types live in `src/lib/types/` and `src/types/` |
| Pre-envelope contract binding (risk R3) | `src/lib/types/api.ts:9-13` declares `{data, next_cursor, has_more}`; the frozen contract is `{data, meta:{cursor, has_more, limit}}`. Dates are scalars, not `HistoricalDate` |
| 401 handling contradicts the contract | `src/lib/api/axios.ts:38-56` signs the user out on **any** 401. `docs/contracts/error-codes.md` requires: refresh once, then sign out; and never refresh/sign-out on 403 |
| SSR context is a stub | `src/infrastructure/http/request-context.ts:19` returns `{locale:'vi'}` on the server — no `X-Current-Clan-Id`, wrong locale |
| No observability at all | `grep -E "sentry|opentelemetry|logger|trace" web/src` returns zero matches |
| Thin tests (risk R11) | Two files total: `tests/behavior/`, `tests/contracts/`. No component or E2E harness |
| Backend has logs but no correlation | `app/core/logging.py` emits JSON and `SentryMiddleware` is wired, but `grep -E "request_id\|correlation\|traceparent" backend/app` returns zero matches; CORS exposes no headers; no RED metrics |

Size: `web/src` is 134 files / ~7.6k LOC. Small enough to restructure decisively, large
enough that leaving two coding styles in place would be costly.

### 1.2 Programme decomposition

The original request spans four independent subsystems. Each gets its own
spec → plan → implementation cycle:

| | Sub-project | Status |
|---|---|---|
| **A** | Web architecture spine + contract migration + observability | **this document** |
| B | Design system & UX for all ages (Arbor Heritage tokens, accessibility) | next |
| C | Observability | **folded into A** — the correlation seam lives in the HTTP client A rewrites |
| D | Mobile wiring & restructure (Dio, DI flip mock→API, merge the two `domain/` roots) | after B |

Agreed order: **A (+C) → B → D**.

### 1.3 Assumption

The web client has no real users yet. Rebuilding its data layer is therefore cheap, and
no migration/compatibility window is needed. If this is wrong, the slice ordering in §5.1
still works but each PR needs a feature flag.

## 2. Decisions

| # | Decision | Rejected alternative and why |
|---|---|---|
| D1 | Real domain layer + typed repositories; **no** port-interface/use-case class per CRUD op | Full hexagon symmetry with the backend — an `interface` with exactly one implementation is ceremony, not dependency inversion. Also rejected: flattening to hooks-only, which would leak kinship/date logic into components and duplicate it against mobile |
| D2 | Feature-sliced layout; components move into `features/<slice>/ui` in A, look & feel unchanged | Leaving components untouched until B — would mean touching the same files twice |
| D3 | W3C `traceparent` propagated FE→BE, exported through Sentry tracing | Full OpenTelemetry + self-hosted collector (operational cost too high for this team); bare `X-Request-Id` (no intra-request waterfall) |
| D4 | Generate TS types from backend `/openapi.json`, commit them, verify freshness in CI; hand-write zod at the boundary | Full client codegen (orval/openapi-zod-client) — generators do not express `profile`/`include`/`fields` sparse-fieldset semantics, so the output would need hand-wrapping anyway. Hand-written zod alone — drift detection would again depend on someone remembering to write a test, which is how R3 happened |
| D5 | Vitest + RTL + MSW + Playwright | Skipping E2E — middleware, locale prefix, cookie and clan-context bugs only surface end to end |
| D6 | Server Components fetch first paint, hydrate into TanStack Query; client owns pagination/search/mutations | Client-only (blank first paint on weak devices — the exact audience B targets); server-only + Server Actions (the XYFlow tree and infinite scroll need client state anyway) |
| D7 | Migrate **all** slices, one PR per slice, deleting legacy in the same PR | Spine + two sample slices — leaves the repo in the half-migrated state that caused the current mess |

## 3. Target structure

```
web/src/
├── app/[locale]/…              # routing only: layout, page, loading, error, not-found
│                               # page.tsx calls a feature loader, renders feature UI
├── domain/                     # plain TypeScript: no React, Next, fetch, or zod
│   ├── shared/                 # ClanId, LocaleCode, DomainError, Result
│   ├── date/historical-date.ts # precision, date-vs-display selection, compare, lunar
│   ├── person/                 # Person, Gender, LifeStatus, invariants
│   ├── kinship/                # generation (đời), relationship labels per locale, polygyny order
│   └── capability/             # role + clan state → capabilities
├── features/<slice>/           # persons · relationships · tree · events · documents
│   │                           # · auth · admin · platform · backoffice
│   ├── api/
│   │   ├── <x>.dto.ts          # zod schemas, constrained to the generated OpenAPI types
│   │   ├── <x>.repository.ts   # fetch → parse → map DTO to domain
│   │   └── <x>.keys.ts         # TanStack query keys, single source
│   ├── model/                  # ONLY where real orchestration exists
│   ├── server/                 # Server Component loaders (prefetch / hydrate)
│   ├── hooks/                  # TanStack Query, client only
│   ├── ui/                     # this feature's components
│   └── index.ts                # PUBLIC SURFACE — the only import path for other code
├── shared/
│   ├── http/                   # api-client, request-context, envelope, errors, refresh
│   ├── telemetry/              # logger, trace, Sentry, Web Vitals
│   ├── ui/                     # shared primitives (moved from components/ui); B replaces internals
│   ├── i18n/  config/  testing/
│   └── state/ui.store.ts
└── generated/api-types.ts      # generated from /openapi.json, committed, CI-verified
```

### 3.1 Dependency rules

Machine-enforced, not a convention:

| Layer | May import | Must not import |
|---|---|---|
| `domain/**` | `domain/**` only | react, next, zod, fetch, tanstack, zustand, supabase |
| `features/*/api` | `domain`, `shared/http`, `generated` | react, ui, hooks, other features |
| `features/*/hooks`, `server`, `model` | own `api` + `domain`, `shared/**` | other features' internals |
| `features/*/ui` | own `hooks`/`model`, `domain`, `shared/ui` | `api` (no direct transport) |
| `features/A` | `features/B` **via `index.ts` only** | `features/B/api/...` |
| `app/**` | `features/*/index.ts`, `shared/**` | `api` directly |
| anything | — | `app/**` |

Enforced by **dependency-cruiser** in CI — the frontend counterpart of the backend's
`lint-imports` ratchet (ADR-013).

### 3.2 Deleted when A completes

`src/lib/api/`, `src/lib/hooks/`, `src/application/`, `src/infrastructure/`, `src/types/`,
`src/lib/types/`, `src/components/<feature>/`, and the `axios` dependency.

### 3.3 Why this is still DDD/SOLID

Dependency inversion at the frontend is already provided by module boundaries plus types.
The places where SOLID earns its keep here are: the domain not knowing about transport
(SRP/DIP), the mapper being the single place that knows the backend shape (OCP when the
backend adds fields), and each feature's `index.ts` being a genuine segregated interface.

## 4. The spine

### 4.1 Request context, both runtimes

```
shared/http/request-context.ts   # type RequestContext { locale, clanId?, accessToken?, traceparent }
shared/http/context.server.ts    # cookies() / headers() + Supabase SSR client   (RSC only)
shared/http/context.client.ts    # auth.store + Supabase browser client          (client only)
```

**Required change:** the current clan moves from `localStorage` to a cookie
(`current_clan_id`, `SameSite=Lax`) — the server cannot read `localStorage`. `auth.store`
remains the client-side source of truth but writes the cookie whenever the clan changes.
`src/middleware.ts` uses the same cookie to redirect users with no selected clan, instead
of letting each page discover it.

### 4.2 HTTP client: `fetch`, drop axios

axios cannot run cleanly inside Server Components and its current interceptors are bound
to `window`. Replaced by a thin `apiFetch` over standard `fetch`:

- attaches `Authorization`, `Accept-Language`, `X-Current-Clan-Id`, `traceparent`
- timeout via `AbortSignal.timeout`
- supports `next: { tags }` for RSC cache and revalidation
- one implementation usable from RSC, client, and Playwright

### 4.3 Envelope and pagination

`shared/http/envelope.ts` unwraps `{data}` / `{data, meta}` into an internal type:

```ts
type Page<T> = { items: T[]; cursor: string | null; hasMore: boolean; limit: number }
```

No `next_cursor` reaches application code. Cursors stay opaque — repositories never parse
them; on `400 invalid_cursor` the hook drops the cursor and refetches page one, per
contract.

`HistoricalDate` becomes a domain model with rendering behaviour (`date` when
`precision === 'exact'`, else `display`, falling back to `date`) instead of each component
re-implementing the rule.

### 4.4 Error taxonomy

| Class | Trigger | Behaviour |
|---|---|---|
| `ApiError` | any `{error:{code,message,detail}}` | preserves `code` + `traceId`; UI branches on `code`, never on `message` |
| 401 | credential | refresh **once**, single-flight across concurrent 401s, retry; sign out only if refresh fails |
| 403 | policy | route by code per `docs/contracts/error-codes.md`: `email_not_verified` → resend screen, `clan_suspended` → blocked screen + clan switcher, `no_approved_clan_membership` → onboarding, others → hide/disable the action with a permission notice |
| `NetworkError` / timeout | transport | offer retry, keep currently displayed data |

`message` arrives already localized via `Accept-Language`, so it is displayed directly; the
frontend keeps a per-code fallback table for offline cases only.

### 4.5 Observability

**Backend** — additive, no contract change:

- `TraceContextMiddleware`: accept an inbound `traceparent`, generate one otherwise; store
  in a ContextVar alongside the existing `RequestMeta`
- `app/core/logging.py` adds `trace_id`, `span_id`, route and `clan_id` to every JSON line
- Sentry init continues the inbound trace so the web span and the API span form one trace
- return `traceparent` as a response header and add it to CORS `expose_headers` (currently
  `allow_headers=["*"]` but nothing is exposed). The response envelope is untouched, so no
  contract change is needed
- RED metrics via `prometheus-fastapi-instrumentator` at `/internal/metrics`, disabled by
  default, enabled by env var and guarded by an internal token

**Web:**

- `shared/telemetry/`: Sentry for both the browser and the Next server runtime, with
  `tracePropagationTargets` pointing at the API origin so trace headers propagate
- structured logger `logger.info({ event, traceId, route, clanId })` — printed in dev,
  shipped as Sentry breadcrumbs/logs in production. No scattered `console.log`
- Web Vitals via `useReportWebVitals` (LCP/INP/CLS) — the measurement B needs for its
  "works on old phones and weak networks" goal
- user-facing errors show a short trace id so a member can read it out to an admin, who can
  then find the exact backend log line

The trace-context choice is an architectural decision and ships as
`docs/decisions/033-w3c-trace-context-sentry.md` in the same PR.

## 5. Delivery

### 5.1 PR sequence

| # | PR | Contents | Outcome |
|---|---|---|---|
| 0 | **Spine** | `generated/api-types.ts` + generation script · `shared/http/*` · `domain/shared`, `domain/date` · `shared/telemetry` · dependency-cruiser · vitest + RTL + MSW + Playwright · **backend**: trace middleware, trace_id in logs, exposed header, `/internal/metrics`, `033-w3c-trace-context-sentry.md` | Pattern and gates exist; no screen touched |
| 1 | **auth** | `current_clan_id` cookie, `auth.store` rewritten around the context, capabilities, middleware on the cookie, 403 screens (unverified email / suspended clan / pending approval) | Login loop matches the contract; later slices get a trustworthy context |
| 2 | **persons** | full reference slice: dto/repo/keys/server loader/hooks/ui, `domain/person`, `HistoricalDate` on screen | Reference pattern for the rest |
| 3 | **relationships** | marriages, parent-child, two-sided spouse order | |
| 4 | **tree** | tree read-model + focus, XYFlow, `domain/kinship`, generation | Heaviest slice, done once the pattern is stable |
| 5 | **events** | anniversaries, `next_occurrence`, lunar dates | |
| 6 | **documents** | upload, soft delete, visibility | |
| 7 | **admin + platform + backoffice** | member approval, invitations, audit, platform metrics | `lib/api`, `lib/hooks`, `application/`, `infrastructure/`, `axios` all deleted. R3 closed |

Each PR migrates its slice **and** deletes the corresponding legacy code. No PR only adds.

### 5.2 Test strategy

| Layer | Tool | Covers |
|---|---|---|
| `domain/**` | Vitest | HistoricalDate (5 precisions × lunar × null), generation computation, relationship labels, capabilities per role. No DOM, no network |
| `features/*/api` | Vitest + fixtures taken from the contract docs | DTO→domain mappers, envelope unwrapping, `Page<T>`, `400 invalid_cursor` |
| `features/*/hooks`, `ui` | RTL + MSW | MSW serves the **real envelope shape**, so hooks and components can never be tested against an invented shape. Includes error paths: 401 refresh, 403 routing, broken cursor |
| End to end | Playwright + real backend via docker compose | four journeys: login → select clan → view tree → edit member; switch clan; view documents; approve a member. The only place middleware / locale-prefix / cookie bugs surface |
| Clan isolation | Playwright | two accounts in two clans; A cannot see B's data — verified in both directions, matching backend discipline |

### 5.3 CI gates

```
pnpm type-check
pnpm lint
pnpm depcruise          # §3.1 dependency rules
pnpm test:unit
pnpm test:component
pnpm test:e2e           # PRs 1/2/4 and main (PR 0 ships no screens)
pnpm gen:api && git diff --exit-code src/generated
```

The last line is the anti-R3 mechanism: CI boots the backend, fetches `/openapi.json`,
regenerates types, and **fails if the backend shape changed without the frontend keeping
up** — instead of breaking at runtime.

Both `test:e2e` and `gen:api` need the backend running, so CI stands it up once via
docker compose and reuses it for both steps.

### 5.4 Documentation updated in the same PRs

`docs/sad/05b-web-components.md` (its C4 diagram describes the old structure),
`web/CLAUDE.md`, `docs/sad/08-crosscutting-concepts.md` (observability section),
`docs/sad/11-risks-and-technical-debt.md` (close R3 and R11), `docs/decisions/033-*.md`.

## 6. Risks

- **PR 4 (tree)** is the most likely to slip: XYFlow plus the tree read-model plus
  performance on clans of several thousand people. Scheduled last among the read slices so
  the pattern is settled by then.
- **Moving the clan id to a cookie** touches middleware, `auth.store` and the clan-select
  screen simultaneously. Contained in PR 1 and covered by E2E.
- **Playwright needs a running backend in CI.** If the current CI cannot stand up
  Postgres + backend, E2E runs on main only — and that limitation is stated explicitly
  rather than silently dropped.
- **`/internal/metrics` has no scraper yet.** It is preparation, not a finished solution;
  dashboards rely on Sentry until a scraper exists.

## 7. Out of scope

Visual design, design tokens, accessibility work and age-friendly UX (sub-project B);
all mobile work (sub-project D); backend business logic; infrastructure and Pulumi.
