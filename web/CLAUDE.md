# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Package manager is **pnpm 10** (pinned via `packageManager`). All scripts:

```bash
pnpm install                                   # install deps
pnpm dev                                       # Next dev server on :3000
pnpm build && pnpm start                       # production build + serve
pnpm type-check                                # tsc --noEmit (strict)
pnpm lint                                      # eslint .
pnpm lint:fix
pnpm format                                    # prettier --write . — DO NOT run: 112 pre-existing files have drift (§3.2 of the work register); it would bury any real diff
pnpm format:check
pnpm depcruise                                 # dependency-cruiser — enforces the layer rules below, CI-gated
pnpm gen:api [path/to/openapi.json]            # regenerate src/generated/api-types.ts from the backend's OpenAPI schema; no arg hits a running backend, a path arg reads a dumped schema (what CI uses)
pnpm test:unit                                 # vitest --project unit (node environment, *.test.ts under src/)
pnpm test:component                            # vitest --project component (jsdom, *.test.tsx, RTL + MSW)
pnpm test:e2e                                  # playwright test — boots `next dev` on :3100 itself
pnpm test:e2e:ui                                # playwright test --ui
pnpm test:behavior                             # legacy: node --test on tests/behavior/*.test.ts (TS via --experimental-strip-types)
pnpm test:contracts                            # legacy: node --test on tests/contracts/*.test.mjs
```

Full gate before calling anything done: `pnpm type-check && pnpm lint && pnpm depcruise && pnpm test:unit && pnpm test:component && pnpm test:e2e && pnpm build`. Verify `pnpm lint` with the plain command — a clean run prints nothing, which is easy to misread as "didn't run."

Env vars in `.env.local` (see `.env.example`): `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_API_ORIGIN`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

## Architecture

Two trees coexist during the migration described in
`docs/superpowers/specs/2026-08-02-web-architecture-observability-design.md`:

- **Legacy, pre-envelope** — `src/lib/api/`, `src/lib/hooks/`, `src/application/<feature>/`,
  `src/infrastructure/<feature>/` (feature slices: `admin`, `auth`, `documents`, `events`,
  `persons`, `relationships`, `tree`) plus the `axios` dependency. Scaffolded against
  unwrapped bodies, `next_cursor`, scalar dates and `*_approx` flags — **not** the frozen
  contract. Being deleted slice by slice by the feature PRs that follow this one. Do not add
  to it.
- **Target (the spine)** — built by this PR, landed on by every feature PR after it:

  ```
  web/src/
  ├── app/[locale]/…          # routing only: layout, page, loading, error, not-found
  ├── domain/                 # plain TypeScript: no React, Next, fetch, zod, tanstack,
  │                           # zustand, or supabase — shared/, date/, and (as features
  │                           # land) person/, kinship/, capability/
  ├── features/<slice>/       # one per slice PR: persons, relationships, tree, events,
  │   │                       # documents, auth, admin, platform, backoffice
  │   ├── api/                # transport only — calls apiFetch, no React
  │   ├── model/              # zod DTOs constrained to the generated OpenAPI types
  │   ├── server/             # repository: fetch → parse → map to domain; query keys
  │   ├── hooks/              # TanStack Query hooks
  │   ├── ui/                 # components — never import this slice's own api/
  │   └── index.ts            # PUBLIC SURFACE — the only import path for other code
  ├── shared/
  │   ├── http/               # api-client, request-context, envelope, errors, refresh
  │   ├── telemetry/          # logger, trace, Sentry, Web Vitals
  │   └── testing/            # MSW + RTL harness
  └── generated/api-types.ts  # generated from /openapi.json, committed, CI-verified
  ```

  `src/features/` does not exist yet — it lands with the first feature slice PR. New code
  that isn't a feature slice belongs in `src/domain/` or `src/shared/http/`, never in the
  legacy trees above.

Path alias `@/*` → `./src/*` (tsconfig).

### Dependency rules

**What the machine actually checks.** `.dependency-cruiser.cjs` holds nine rules, run by
`pnpm depcruise` and gated in CI. Every one of them *forbids* something — dependency-cruiser
has no allow-list concept — so a rule name is the thing to grep for when a build fails:

| Rule | Forbids | Severity |
|---|---|---|
| `domain-is-pure` | `src/domain/**` importing any npm package except `typescript` / `@types/*` — which covers react, next, zod, tanstack, zustand and supabase | error |
| `domain-imports-only-domain` | `src/domain/**` importing anything under `src/` that is not `src/domain/` | error |
| `api-layer-has-no-react` | `features/*/api/**` importing `react`, `react-dom` or `@tanstack/react-query` | error |
| `ui-does-not-call-transport` | `features/X/ui/**` importing `features/X/api/**` | error |
| `cross-feature-only-via-index` | reaching into another feature's internals; `features/B` is importable only through `features/B/index.ts` | error |
| `app-does-not-call-transport` | `src/app/**` importing `features/*/api/**` | error |
| `nothing-imports-app` | anything outside `src/app/` importing `src/app/**` | error |
| `no-circular` | import cycles | error |
| `no-orphans` | modules nothing imports — 3 known and accepted today | **warn** |

The exit code is the count of error-level violations, so one error returns 1. Warnings do
not fail the build.

**What is convention, not a gate.** The permitted direction of imports — `api` reaching
`domain`/`shared/http`/`generated`, `hooks`/`server`/`model` reaching their own `api` plus
`shared/**`, `ui` reaching its own `hooks`/`model`, `app/**` reaching `features/*/index.ts`
— is architecture, not a rule. Nothing stops you importing `shared/telemetry` from a
`model`. Follow it anyway; the rules above only catch the directions that were worth the
cost of encoding.

`src/shared/` is `http/`, `telemetry/` and `testing/`. There is no `shared/ui/` — reusable
presentational components currently live in `src/components/ui/`, and moving them is a
sub-project B decision that has not been made.

The legacy trees (`src/lib/api`, `src/lib/hooks`, `src/application`, `src/infrastructure`,
`src/types`) are excluded from these rules — they are being deleted, not refactored into
compliance.

### The spine (`src/shared/http/`, `src/shared/telemetry/`, `src/domain/date/`)

- `apiFetch` (`src/shared/http/api-client.ts`) is the **only** way to reach the backend.
  It attaches `Authorization`, `Accept-Language`, `X-Current-Clan-Id`, and a `traceparent`;
  applies a timeout via `AbortSignal.timeout`; and distinguishes a caller-initiated abort
  from a transport failure.
- Request context (`RequestContext`) is always **passed in**, never read from a global —
  `context.server.ts` builds it from `cookies()` + Supabase SSR in an RSC,
  `context.client.ts` builds it from the auth store + Supabase browser client. The same
  repository function runs, and is tested, in both runtimes.
- `unwrapData` / `unwrapPage` (`src/shared/http/envelope.ts`) are the **only** readers of
  the `{"data": ...}` / `{"data": ..., "meta": {...}}` envelope. No component ever sees the
  wrapped shape. `unwrapPage` rejects the pre-envelope `{data, next_cursor, has_more}` shape
  outright. Cursors are opaque — never parsed or constructed; on `400 invalid_cursor`, drop
  the cursor and refetch page one.
- The UI branches on the error **`code`**, never on `message` — `message` arrives already
  localized from the backend (`src/shared/http/errors.ts`, `ApiError` / `NetworkError` /
  `MalformedResponseError`).
- 401 triggers a single-flight refresh-then-retry (`src/shared/http/refresh.ts`); 403 never
  refreshes — it is a policy decision, not a stale credential.
- `HistoricalDate` (`src/domain/date/historical-date.ts`) owns its own render rule (`date`
  when `precision === 'exact'`, else `display`, falling back to `date`); no component
  re-implements it.

### Routing, locales, auth gating

- next-intl with locales `vi | en | zh | fr`, **default `vi`**, `localePrefix: 'always'` — every route is prefixed (`/vi/...`, `/en/...`). See `src/i18n/routing.ts` and `messages/*.json`.
- Route groups under `src/app/[locale]/`: `(auth)` (login/register/callback/pending-approval — public), `(dashboard)` (protected), plus `backoffice/`, `platform/`, `select-clan/`.
- `src/middleware.ts` runs the intl middleware first, strips the locale prefix, lets `PUBLIC_ROUTES` through, and for everything else creates a Supabase SSR client (`@supabase/ssr`) and redirects to `/<locale>/login` when there is no session. If Supabase env vars are missing the auth check is skipped — be aware in local dev.
- **After the session check, `src/middleware.ts` gates `CLAN_SCOPED_SEGMENTS` (`dashboard`, `documents`, `events`, `members`, `tree`, `admin` — everything under the `(dashboard)` route group) on the `current_clan_id` cookie.** Missing and unparseable (not a UUID) are the same case, both read as "no clan selected" through `parseClanCookie` (`src/shared/http/request-context.ts`), and both redirect to `/<locale>/select-clan` rather than letting the route render and fire a clan-scoped `apiFetch` call with no `X-Current-Clan-Id`. `platform/*`, `backoffice/*`, and `select-clan` itself are deliberately not gated: the first two are cross-clan super-admin surfaces (`docs/architecture/multi-tenancy.md`), and gating the picker page would loop. Landed by seed S-023; see `web/src/middleware.test.ts`.

### The `current_clan_id` cookie (S-023)

The cookie is the single source for the active clan: `context.server.ts` reads it through
`cookies()`, `context.client.ts` reads the identical value through `document.cookie`, and
both run it through the same `parseClanCookie` (`src/shared/http/request-context.ts`) so a
Server Component and a browser session never disagree about which clan is active. A
`localStorage`-only value (the legacy path's third fallback) is invisible to a Server
Component, which is the whole reason this moved to a cookie.

**Attributes, decided once in `context.client.ts` so nine later seeds (S-024 through S-033)
inherit them rather than re-deciding:**

| Attribute | Value | Why |
|---|---|---|
| `httpOnly` | not set (false) | Forced, not chosen: `context.client.ts` reads the cookie through `document.cookie`, and a script that can read a cookie can set it, so declaring `httpOnly` would be theatre. The cookie is also not a credential — the backend re-validates it against the caller's actual memberships on every request (`get_current_clan_id`) — so nothing sensitive leaks by it being script-readable. |
| `sameSite` | `lax` | Sent on a normal top-level navigation, withheld on a cross-site subrequest or form post — the standard mitigation for a script-writable cookie. Matches the legacy writer, `src/infrastructure/auth/clan-selection-storage.ts`. |
| `secure` | only when `location.protocol === 'https:'` | `document.cookie` silently drops a hard-coded `Secure` attribute set from an insecure origin rather than erroring, which would break local `http://localhost` dev instead of protecting anything. |
| `path` | `/` | Every locale-prefixed route reads it, and so does `src/middleware.ts`, which runs before any narrower path is known. |
| `max-age` | one year | A UI preference the backend re-validates, not a session credential — no security reason to expire it sooner. |

`parseClanCookie` treats the value as unparseable unless it matches the UUID shape every
`clan_id` takes in the backend (cast `::uuid` throughout `docs/architecture/data-model.md`),
and returns `null` rather than forwarding garbage as `X-Current-Clan-Id`.

**What still writes the cookie, and why that is not a gap.** The `select-clan` flow still
writes through the legacy `persistCurrentClanId` (`src/infrastructure/auth/clan-selection-storage.ts`)
— same cookie name, compatible attributes — because rewiring `useAuth`'s `selectClan` onto the
spine is S-025's job (rewriting the auth store around this context), not S-023's. `context.client.ts`
exports `writeClanCookie` / `clearClanCookie` as the canonical writer S-025 adopts, so the
attributes above stay decided in one place rather than drifting between two writers.

**No `features/` repository exists yet to write a cross-runtime test against** (`src/features/`
lands with S-024 onward). `src/shared/http/context.test.tsx` proves the closest thing that
exists today: `getServerRequestContext` and `getClientRequestContext` resolve the same
`clanId` for one cookie, and a bare `apiFetch` call — what a repository function does under the
hood — carries the identical `X-Current-Clan-Id` from both. Read the file's own comment before
assuming a later slice's repository test can copy this shape verbatim; it is a stand-in, not the
real pattern.

### Backend contract — required headers and query semantics

All clan-scoped requests must send:

- `Authorization: Bearer <token>`
- `Accept-Language`
- `X-Current-Clan-Id`

**New code:** route through `apiFetch` (`src/shared/http/api-client.ts`), which builds these
headers plus `traceparent` from a `RequestContext` (`src/shared/http/request-context.ts`,
`context.server.ts`, `context.client.ts`) — never assemble them ad-hoc.

**Legacy code only:** the shared Axios client `src/lib/api/axios.ts` attaches all three via
interceptors. On `401` it signs out and redirects to `/<locale>/login`. The clan id comes
from `getRequestContext()` (`src/infrastructure/http/request-context.ts`), which reads in
order: `useAuthStore.currentClanId` → `user.clan_id` → `localStorage.current_clan_id`. SSR
returns a minimal context (`{ locale: 'vi' }`). Do not extend this path — it is being
deleted by the slice PRs.

Query semantics that must be preserved when touching list/detail endpoints:

- Every 2xx response is wrapped in the canonical envelope: `{"data": ...}`; lists are `{"data": [...], "meta": {"cursor", "has_more", "limit"}}` (cursor pagination, opaque cursors)
- Date fields arrive as `HistoricalDate` objects `{date, precision, display, lunar}` — render `date` when `precision === "exact"`, else `display`
- `profile=summary|detail|full`
- `include` for compound documents
- `fields` for sparse fieldsets
- **Batch include gotcha**: keys from `include_by_id` must be merged into the sparse `fields` set, or compound includes will be dropped.

⚠️ The existing clients (`src/lib/api/auth.ts`, `src/infrastructure/**`, member/tree types and forms) were scaffolded against the **pre-envelope** shapes (unwrapped bodies, `next_cursor`, scalar dates, `*_approx` flags) and have not yet been adapted — adopting the frozen contracts in `docs/contracts/*` is a pending, deliberate migration. Write new code against the envelope shapes above.

### State management split

- **Server state**: TanStack Query (`src/lib/hooks/use*.ts`). Cross-feature invalidation helpers live in `src/lib/hooks/query-invalidation.ts`.
- **Client state**: Zustand — `src/store/auth.store.ts` (session, current clan), `src/store/ui.store.ts`.
- Forms: react-hook-form + zod resolvers.

### UI

Tailwind + Radix primitives. Reusable primitives in `src/components/ui/`; feature components in `src/components/<feature>/`. Mind the Arbor Heritage design mandates referenced in the repo-root `CLAUDE.md`.

### Testing

Four harnesses, one gate each:

- `pnpm test:unit` — Vitest, node environment, `*.test.ts` under `src/`. Pure domain and
  `shared/http` logic: `HistoricalDate`, envelope unwrapping, the error taxonomy, request
  context, trace id generation, single-flight refresh, `apiFetch`, the logger.
- `pnpm test:component` — Vitest, jsdom, `*.test.tsx`. React Testing Library + MSW
  (`src/shared/testing/`); MSW handlers build real envelopes, so a test cannot invent a
  response shape.
- `pnpm test:e2e` — Playwright (`web/playwright.config.ts`, `web/e2e/`). Boots `next dev` on
  `:3100` itself; runs desktop Chrome and a Pixel 5 viewport. Four specs, and
  `pnpm test:e2e --list` counted 36 tests on 2026-08-21 (18 cases across the two projects):
  - `smoke.spec.ts` — locale redirect, the login form renders, and (since seed S-022 fixed
    `R-lang`, see `docs/sad/11-risks-and-technical-debt.md`) `<html lang>` tracking the route
    locale on both `/vi/login` and `/en/login`.
  - `fonts.spec.ts` — the two mandated typefaces reach the screen (seed S-002). A computed
    style in a real browser is the only thing that can see a dead `font-family`.
  - `text-scale.spec.ts` — `T-04`: no horizontal page scroll at 320 px width and 200% root
    font size (seed S-034). jsdom has no layout engine, so no other harness can measure a box.
  - `dark-theme.spec.ts` — the dark palette reaches `body` under an emulated dark colour
    scheme, and no class or attribute is involved (seed S-006, ADR-045). The stylesheet holds
    both palettes and cannot tell you which one won the cascade; only an engine can.

  These four cover what only a browser can measure. Real user journeys arrive with the
  feature slices, once there is a backend to talk to.
- `tests/behavior/` (legacy) — Node test runner with `--experimental-strip-types` for `.ts`.
  Focused on auth + query invalidation flows against the legacy trees; not part of the CI
  gate for new code.
- `tests/contracts/` (legacy) — `.mjs` contract tests that pin the legacy API client shapes.

CI (`.github/workflows/web-ci.yml`) runs type-check, lint, `depcruise`, unit, component,
build, e2e, and `api-types-fresh` (regenerates `src/generated/api-types.ts` from the
backend's OpenAPI schema and fails the build if it drifts — the anti-R3 gate). The
freshness job is triggered by changes under either `web/**` or `backend/app/**`, so a
backend-only PR that changes response shapes cannot skip it.

## Migration notes

- `src/lib/api/*.ts`, `src/lib/hooks/use*.ts`, `src/application/<feature>/`, and
  `src/infrastructure/<feature>/` predate the envelope contract and the spine built above.
  They are frozen, not extended: no new feature should add to them, and each is deleted
  outright when the matching feature slice PR lands (§3.2 of the architecture spec).
- `src/domain/` is currently `shared/` plus `date/` (the `HistoricalDate` model added by the
  spine PR). As features land, domain types move out of `src/types/` and `src/lib/types/`
  into `src/domain/<feature>/`.
- New transport code goes in `src/shared/http/` (or, once a feature slice PR lands,
  `src/features/<slice>/api/`) — never in `src/lib/api/` or `src/infrastructure/`.
