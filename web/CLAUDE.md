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

**`pnpm test:e2e` does not need `.env.local`, and this is a gate guarantee, not an
accident (S-041, 2026-08-22).** `.env.local` is untracked — `git ls-files web/.env.local`
returns nothing — so it exists in a primary checkout and is absent in every `git worktree`.
Before S-041, that made the gate answer a question about the runner's filesystem: with the
file, `pnpm test:e2e` passed 38/38; without it, `e2e/text-scale.spec.ts` failed 4 of 38, on
both `/vi/login` and `/vi/register` in both Playwright projects, because the two
`NEXT_PUBLIC_SUPABASE_*` variables were missing, `SupabaseSetupNotice.tsx` rendered the
missing-Supabase banner, and the banner itself overflowed the 320px/200%-text-scale viewport
(`documentElement.scrollWidth` 569 against `clientWidth` 320) — a real defect, but not the one
`text-scale.spec.ts` exists to police, and invisible to CI because CI already exported both
variables on the `e2e` job (`.github/workflows/web-ci.yml`).

`web/playwright.config.ts`'s `webServer.env` now supplies both variables as obvious
placeholders (`https://e2e-fake-project.example.supabase.co`, `e2e-fake-anon-key`) whenever the
shell running the tests has not already exported them, so **the e2e dev server on :3100 always
sees the two variables, in a fresh clone, in a worktree, and in CI**, regardless of whether
`.env.local` exists. Next.js's own env-file loader never overwrites a variable already present
in `process.env` when the process starts, so this wins over `.env.local` even in a primary
checkout that has one — deliberately: no e2e spec talks to a live Supabase backend, so the run
must not depend on real credentials, and a result that only holds where a stray file happens to
exist is the exact defect this closed. Real Supabase env in `.env.local` still governs `pnpm dev`
on :3000 for manual local development; only the self-booted :3100 e2e server is affected. One
caveat this does not cover: `reuseExistingServer: !process.env.CI` means a dev server already
running on :3100 from an earlier manual `pnpm dev --port 3100` is reused as-is, with whatever env
it already has — this only guarantees the placeholders when Playwright starts the server itself.

**What this gate does not guarantee.** The missing-Supabase banner's own text-scale overflow is
untouched — supplying the variables makes the banner stop rendering in this suite, it does not
fix it. That defect is **S-042**, which adds a spec case that deliberately unsets the two
variables for one test so the banner can be measured at all; it is not blocked by anything this
change does, because the placeholders live in `webServer.env`, a plain object a later spec or a
second `webServer` entry can override or bypass, not baked into a build artifact.

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

**The cookie is now the only writer too (S-025).** `useAuth`'s `selectClan` and
`syncAuthContext` (`src/lib/hooks/useAuth.ts`) call `writeClanCookie` / `clearClanCookie`
directly. The legacy `persistCurrentClanId` / `clearCurrentClanId`
(`src/infrastructure/auth/clan-selection-storage.ts`) are unused now — nothing imports
them — because they also wrote `localStorage.current_clan_id`, which S-025's end state
forbids. The file is left in place rather than deleted: deleting the legacy auth transport
is S-027's job, and `pnpm depcruise`'s `no-orphans` check is a warning, not a gate, so an
unused legacy file costs nothing until S-027 removes it.

**No `features/` repository exists yet to write a cross-runtime test against** (`src/features/`
lands with S-024 onward). `src/shared/http/context.test.tsx` proves the closest thing that
exists today: `getServerRequestContext` and `getClientRequestContext` resolve the same
`clanId` for one cookie, and a bare `apiFetch` call — what a repository function does under the
hood — carries the identical `X-Current-Clan-Id` from both. Read the file's own comment before
assuming a later slice's repository test can copy this shape verbatim; it is a stand-in, not the
real pattern.

### Clan capabilities (`src/domain/capability`, S-024)

`src/domain/capability/capability.ts` maps each clan role (`admin`, `editor`, `viewer`) to the
`CapabilitySet` it holds, taken from `docs/architecture/rbac.md`'s permission matrix — one capability
per matrix row where at least one role is denied, each cited to its row in a doc comment. It is pure:
no React, no store, no `apiFetch`, enforced by `domain-is-pure` and `domain-imports-only-domain`.
**The backend still enforces the real check on every request**; this module only decides what the
client offers to render.

**Do not replace the table with a role-hierarchy comparison, even though every row looks nested.**
`docs/architecture/rbac.md:78` gives `editor` ✅ for deleting an event, while `:70` and `:57` give
`editor` ❌ for deleting a relationship and a person. The nesting is empirical, not guaranteed, and a
hierarchy shortcut would hide that.

**Consumed since S-027 (2026-08-22) — and the `no-orphans` warning above still fires anyway,
which is itself worth recording.** `src/lib/hooks/useCapabilities.ts` now calls
`getCapabilities(role)` here instead of the deleted `deriveCapabilities` in
`src/application/auth/use-cases/capabilities.ts`. The hook keeps its old external shape — the
four capability names (`canEditPersons`, `canUploadDocuments`, `canDeleteDocuments`,
`canEditRelationships`) the four real callers destructure (`grep -rn "useCapabilities()" src`) —
mapped from this module's names, rather than pushing the full 25-key `CapabilitySet` onto those
callers as a drive-by rename. **`pnpm depcruise` on 2026-08-22 still reports 4 warnings, not 3,
and that is the tool's own blind spot rather than a failed rewire.** `.dependency-cruiser.cjs`'s
`LEGACY` pattern (`^src/(lib/(api|hooks)|application|infrastructure|types)/`) is in the
`options.exclude` list, so `src/lib/hooks/**` is not a node in the graph at all — an import
*from* an excluded file draws no edge, so `capability.ts` reads as orphaned no matter how real
its consumer is, for as long as the consumer lives in `lib/hooks`. Confirmed by inspecting
`depcruise --output-type json`'s own module list on 2026-08-22: it contains no `src/lib/hooks/*`
entry at all. The real consumption is proven by `grep -rn "domain/capability/capability"
src/lib/hooks/useCapabilities.ts`, by `pnpm type-check`, and by
`src/lib/hooks/useCapabilities.test.tsx`, not by this warning count — do not read a future "3
warnings" as this having regressed, and do not read today's "4" as the rewire having failed.
Widening `LEGACY` to stop excluding `lib/hooks` would fix the tool's blind spot but was not
attempted here: it would newly subject every file in that tree to orphan-checking in one step,
which is a change to what the gate covers, not a deletion, and is not this seed's to make.

**One behaviour changed on purpose while rewiring.** The deleted legacy module hardcoded
`canDeleteEvents: isAdmin`. This module's own `deleteEvent` entry, cited to
`docs/architecture/rbac.md:78` two paragraphs up, grants `editor` too. `useCapabilities.ts` does
not expose `canDeleteEvents` at all — nothing read it (`grep -rn "canDeleteEvents" src` before
S-027 found only the legacy definition) — so nothing regressed, but the discrepancy is real and
recorded in that hook's own doc comment so a future reader who wires the field back in reaches
for the wider, correct grant rather than reintroducing the narrower one.

### The auth store holds session state only (S-025)

**`src/store/auth.store.ts` no longer has a `currentClanId` field or a `setCurrentClan`
action.** Before S-025 the store held both the session (`user`, `clanMemberships`, the
access-state flags) and the active clan, while the `current_clan_id` cookie (S-023) held
the same clan fact for the server to read — two persisted sources for one fact, since the
store's `zustand/middleware` `persist` wrote `currentClanId` to
`localStorage['auth-store']` alongside the cookie. That is the exact defect this tracker
exists to catch, so the clan id was removed from the store rather than kept in sync with
the cookie.

**The one reactive read is `useCurrentClanId()` (`src/shared/http/context.client.ts`).** It
wraps `useSyncExternalStore` around the `current_clan_id` cookie: `writeClanCookie` and
`clearClanCookie` (same file) notify a module-level listener set after they write the
cookie, since a `document.cookie` write fires no native change event. A component that
calls `useCurrentClanId()` re-renders on every clan switch, which is what lets a TanStack
Query key built from the clan id refetch without a page reload — proved by
`src/shared/http/clan-switch.test.tsx`. A non-reactive one-shot read is
`readCurrentClanId()`, for a caller that is not a component, such as `useAuth`'s
`syncAuthContext`.

**`useAuth()` (`src/lib/hooks/useAuth.ts`) still returns `currentClanId`**, now sourced from
`useCurrentClanId()` rather than the store, so `useClanContext`, `select-clan/page.tsx`, and
every other existing caller of `useAuth().currentClanId` needed no change. `Header.tsx`,
`(dashboard)/tree/page.tsx`, and `useCapabilities.ts` read the clan id directly —
`useCurrentClanId()` for the two client components, since they had no other reason to pull
in the whole of `useAuth()`.

**`selectClan` and `syncAuthContext` write the cookie through `writeClanCookie` /
`clearClanCookie` now, not the legacy `persistCurrentClanId` / `clearCurrentClanId`.** See
"What still writes the cookie" under S-023 above for what that leaves behind.

**The legacy `src/infrastructure/http/request-context.ts` lost its `localStorage` fallback.**
Before S-025 it read, in order, `useAuthStore.currentClanId`, then `user.clan_id`, then
`localStorage.getItem('current_clan_id')` — the exact three-way read S-025's seed names as
what it replaces. It now reads `readCurrentClanId()` (the cookie) then `user.clan_id`, with
no `localStorage` step. This file backs the legacy `axios.ts` interceptor, which is
untouched: fixing the read it depends on was in scope, deleting the file it lives in is
S-027's.

**`grep -rn "localStorage.current_clan_id\|current_clan_id" web/src` after S-025** finds
only the cookie name itself (`request-context.ts`'s `CLAN_COOKIE` constant and its
callers, `middleware.test.ts`'s literal cookie header) and prose referencing S-023/S-025 in
comments — no `localStorage.getItem` or `.setItem` call against that key anywhere in `src`.
`clan-selection-storage.ts`, the file that constant used to live in, is deleted (S-027, below).

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
order (S-025): `readCurrentClanId()` — the `current_clan_id` cookie — → `user.clan_id`. No
`localStorage` step remains. SSR returns a minimal context (`{ locale: 'vi' }`). Do not
extend this path — it is being deleted by the slice PRs.

**S-027 tried to delete `axios.ts`, `src/lib/api/auth.ts`, and
`src/infrastructure/http/request-context.ts` outright, and could only close two of the
three.** Its seed text named all three, plus the auth halves of `application/auth` and
`infrastructure/auth`, as this repository's "no PR only adds" rule applied to PR 1. Enumerating
every importer first (`grep -rln "lib/api/axios\|from 'axios'" src`, 2026-08-22) found `axios.ts`
imported not just by the auth infrastructure but by `src/infrastructure/admin/http-admin-repositories.ts`
(four live pages: `platform/clans`, `platform/metrics`, `admin/users`, `admin/clan`) and, through
`src/lib/api/{documents,events,members,relationships,tree}.ts`, by every other legacy slice's
repositories too. `request-context.ts` backs `axios.ts` the same way for all of them. Deleting
either would have broken the persons, tree, events, documents, and admin halves this same seed's
own "Out of scope" line says stay until their own slice PR — `axios.ts` is the legacy app's one
shared transport, not an auth-only file, and this file's own "Migration notes" section already
said so before S-027 ran; the seed text did not cross-reference it. **What actually left:**
`src/lib/api/auth.ts` (`authApi`, dead — its sole in-code match on `grep -rn "lib/api/auth" src`
was a comment quoting a grep command, not an import) and
`src/infrastructure/auth/clan-selection-storage.ts` (dead per S-025, above). **What stays, and
why it is not a smaller version of "done":** `application/auth/ports/auth-repository.ts`,
`application/auth/use-cases/auth-context.ts`, `infrastructure/auth/http-auth-profile-repository.ts`,
and `infrastructure/auth/supabase-auth-session-port.ts` are the live implementation
`useAuth()`'s session sync, sign-in redirect, onboarding, and clan selection call today — deleting
them needs a spine replacement (`apiFetch` calls where `http-auth-profile-repository.ts` calls
`axios.ts`) that does not exist yet, since `src/features/auth/` has not landed. Building that
replacement as a side effect of a deletion seed would be a materially larger, differently-tested
change than "delete legacy code with a live-behind replacement", so S-027 left it as future work
rather than rewriting it under this seed's name. `axios.ts` and `request-context.ts` leave only
when the last legacy slice PR (persons, tree, events, documents, admin, and then auth's own
transport) replaces its own repository, per this section's existing rule that they are "being
deleted by the slice PRs" — plural, and not yet all landed.

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
- **Client state**: Zustand — `src/store/auth.store.ts` (session only, since S-025 — see
  "The auth store holds session state only" above; the active clan is
  `useCurrentClanId()` over the `current_clan_id` cookie, not the store),
  `src/store/ui.store.ts`.
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
- **`src/lib/api/axios.ts` is one file shared by every slice above, not one file per slice.**
  S-027 (2026-08-22) went looking for it while deleting the legacy auth transport and found
  `src/infrastructure/admin/http-admin-repositories.ts` and every one of
  `src/lib/api/{documents,events,members,relationships,tree}.ts` importing it too
  (`grep -rln "lib/api/axios\|from 'axios'" src`). So it, and the
  `src/infrastructure/http/request-context.ts` it depends on, cannot leave until the **last**
  slice PR lands, not the first — "each is deleted outright when the matching feature slice PR
  lands" above is true per-slice-repository-file, not true of this shared pair. See
  "Backend contract" above for the full account and what S-027 could and could not delete.
- `src/domain/` is currently `shared/` plus `date/` (the `HistoricalDate` model added by the
  spine PR). As features land, domain types move out of `src/types/` and `src/lib/types/`
  into `src/domain/<feature>/`.
- New transport code goes in `src/shared/http/` (or, once a feature slice PR lands,
  `src/features/<slice>/api/`) — never in `src/lib/api/` or `src/infrastructure/`.
- **The auth slice's legacy tree is now split between dead and live, not simply "frozen".**
  S-027 deleted `src/lib/api/auth.ts` and `src/infrastructure/auth/clan-selection-storage.ts`
  outright (both had zero real importers). It left
  `src/application/auth/{ports/auth-repository.ts,use-cases/auth-context.ts}` and
  `src/infrastructure/auth/{http-auth-profile-repository.ts,supabase-auth-session-port.ts}` in
  place: `useAuth()` (`src/lib/hooks/useAuth.ts`) still calls all four for session sync,
  sign-in, onboarding, and clan selection, and no `features/auth/` slice exists yet to replace
  them. Whichever seed builds that slice deletes these four along with `axios.ts` and
  `request-context.ts`, together, once every remaining legacy repository has a replacement —
  not auth's four files alone.
- **`VerifyEmailScreen` (`src/components/auth/VerifyEmailScreen.tsx`) is still unreachable
  from a real sign-in after S-027.** It handles `403 email_not_verified`, which only
  `POST /auth/login` can raise, and the live sign-in path
  (`useAuth().signInWithEmail` → `authSessionPort.signInWithEmail`) calls
  `supabase.auth.signInWithPassword` directly, bypassing the backend endpoint entirely. S-027
  left this path untouched for the same reason it left `http-auth-profile-repository.ts` in
  place: swapping `useAuth()`'s Supabase-direct sign-in for a backend-calling one is the
  auth slice's transport rewrite, not a deletion. The screen stays reachable only by direct
  navigation to `/{locale}/verify-email?email=...` and by its own component test.
