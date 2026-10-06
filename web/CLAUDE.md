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
pnpm format                                    # prettier --write . — the 99-file pre-existing drift (cleared 2026-08-22) is gone; safe to run, but keep it out of a behavioural PR's diff
pnpm format:check                              # prettier --check . — CI-gated since 2026-08-22
pnpm depcruise                                 # dependency-cruiser — enforces the layer rules below, CI-gated
pnpm depcruise:baseline                        # rewrite .dependency-cruiser-known-violations.json, the legacy baseline — see "Migration notes"
pnpm depcruise:ratchet origin/main             # fail if that baseline gained an entry since the merge base, or lists an import that is gone; CI-gated on pull requests
pnpm gen:api [path/to/openapi.json]            # regenerate src/generated/api-types.ts from the backend's OpenAPI schema; no arg hits a running backend, a path arg reads a dumped schema (what CI uses)
pnpm test:unit                                 # vitest --project unit (node environment, *.test.ts under src/, plus the globs vitest.config.mts adds)
pnpm test:component                            # vitest --project component (jsdom, *.test.tsx, RTL + MSW)
pnpm test:e2e                                  # playwright test: boots its own `next dev` servers; see "Two worktrees, one machine"
pnpm test:e2e:ui                                # playwright test --ui
pnpm test:behavior                             # legacy: node --test on tests/behavior/*.test.ts (TS via --experimental-strip-types)
pnpm test:contracts                            # legacy: node --test on tests/contracts/*.test.mjs
```

Full gate before calling anything done: `pnpm type-check && pnpm lint && pnpm format:check && pnpm depcruise && pnpm test:unit && pnpm test:component && pnpm test:e2e && pnpm build`. `pnpm test:e2e:auth` is **not** in that list and is not optional either — it needs Docker, the Supabase CLI stack and a seeded backend, so run it whenever you touch an authenticated route, and say plainly if you could not. See "The authenticated e2e harness". CI runs it too since #193, in `.github/workflows/image-e2e.yml`'s `image-auth-e2e` job, against the built backend image, so a pull request whose author could not run it still gets a reading. Nothing requires that check to pass before a merge, so read it. Verify `pnpm lint` with the plain command — a clean run prints nothing, which is easy to misread as "didn't run."

**`pnpm format:check` has been in CI since 2026-08-22.** Before that, `web/CLAUDE.md`
and `.claude/rules/tailwind.md` § 9 both told contributors not to run `pnpm format`, because 112
files had accumulated pre-existing Prettier drift and a format run would bury the real diff in any
pull request. Re-counted on 2026-08-22: `pnpm format:check` actually named **99** files,
not 112 — the figure had gone stale across three batches that added and deleted files in `web/`
since it was first measured, and nobody had re-run the count. The fix ran `pnpm format --write .`
once, as its own single-purpose commit, landing all 99 files at once and touching nothing else.
`pnpm format` is safe to run now. The caution that follows is about diff hygiene, not about the
tool: running it inside a pull request that also changes behaviour still buries the real diff, so
keep a mechanical formatting pass in its own commit, the way that one did.

Env vars in `.env.local` (see `.env.example`): `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_API_ORIGIN`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

**`pnpm test:e2e` does not need `.env.local`, and this is a gate guarantee, not an
accident (2026-08-22).** `.env.local` is untracked — `git ls-files web/.env.local`
returns nothing — so it exists in a primary checkout and is absent in every `git worktree`.
Before that fix, the gate answered a question about the runner's filesystem: with the
file, `pnpm test:e2e` passed 38/38; without it, `e2e/text-scale.spec.ts` failed 4 of 38, on
both `/vi/login` and `/vi/register` in both Playwright projects, because the two
`NEXT_PUBLIC_SUPABASE_*` variables were missing, `SupabaseSetupNotice.tsx` rendered the
missing-Supabase banner, and the banner itself overflowed the 320px/200%-text-scale viewport
(`documentElement.scrollWidth` 569 against `clientWidth` 320) — a real defect, but not the one
`text-scale.spec.ts` exists to police, and invisible to CI because CI already exported both
variables on the `e2e` job (`.github/workflows/web-ci.yml`).

`web/playwright.config.ts`'s `webServer.env` now supplies both variables as obvious
placeholders (`https://e2e-fake-project.example.supabase.co`, `e2e-fake-anon-key`) whenever the
shell running the tests has not already exported them, so **the hermetic e2e dev server always
sees the two variables, in a fresh clone, in a worktree, and in CI**, regardless of whether
`.env.local` exists. Next.js's own env-file loader never overwrites a variable already present
in `process.env` when the process starts, so this wins over `.env.local` even in a primary
checkout that has one — deliberately: no e2e spec talks to a live Supabase backend, so the run
must not depend on real credentials, and a result that only holds where a stray file happens to
exist is the exact defect this closed. Real Supabase env in `.env.local` still governs `pnpm dev`
on :3000 for manual local development; only the self-booted e2e servers are affected. **The
placeholders hold whenever a spec runs, because since #192 a run only measures a server it
started.** Until then `reuseExistingServer: !process.env.CI` reused any server already answering on
:3100, such as an earlier manual `pnpm dev --port 3100`, as-is and with whatever env it had. Now a
server already answering fails the run before any spec. Only `E2E_REUSE_SERVER=1` reuses one, and a
server reused that way keeps whatever env it was started with. See "Two worktrees, one machine".

**What this gate does not guarantee.** The missing-Supabase banner's own text-scale overflow is
untouched — supplying the variables makes the banner stop rendering in this suite, it does not
fix it. The fix is a spec case that deliberately unsets the two
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
  │   ├── index.ts            # PUBLIC SURFACE — the only import path for other code
  │   └── index.server.ts     # auth only: the server-only half, for src/app (#186)
  ├── shared/
  │   ├── http/               # api-client, request-context, envelope, errors, refresh
  │   ├── supabase/           # the browser and server Supabase clients, and their env
  │   ├── telemetry/          # logger, trace, Sentry, Web Vitals
  │   ├── testing/            # MSW + RTL harness
  │   └── ui/                 # presentational primitives no slice owns
  └── generated/api-types.ts  # generated from /openapi.json, committed, CI-verified
  ```

  `src/features/persons/{model,api}` landed 2026-08-22, the first feature slice; `server/` and
  `hooks/` landed the same day, and so did `ui/`, in two parts — the list/detail screens and the
  create/edit form — see "The `persons` slice" and the two sections below it. New code that isn't a feature slice belongs
  in `src/domain/` or `src/shared/http/`, never in the legacy trees above.

Path alias `@/*` → `./src/*` (tsconfig).

### Dependency rules

**What the machine actually checks.** `.dependency-cruiser.cjs` holds ten rules, run by
`pnpm depcruise` and gated in CI. Every one of them _forbids_ something — dependency-cruiser
has no allow-list concept — so a rule name is the thing to grep for when a build fails:

| Rule                           | Forbids                                                                                                                                                                                                                 | Severity |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| `domain-is-pure`               | `src/domain/**` importing any npm package except `typescript` / `@types/*` — which covers react, next, zod, tanstack, zustand and supabase                                                                              | error    |
| `domain-imports-only-domain`   | `src/domain/**` importing anything under `src/` that is not `src/domain/`                                                                                                                                               | error    |
| `api-layer-has-no-react`       | `features/*/api/**` importing `react`, `react-dom` or `@tanstack/react-query`                                                                                                                                           | error    |
| `ui-does-not-call-transport`   | `features/X/ui/**` importing `features/X/api/**`                                                                                                                                                                        | error    |
| `cross-feature-only-via-index` | reaching into another feature's internals; `features/B` is importable only through `features/B/index.ts`                                                                                                                | error    |
| `app-does-not-call-transport`  | `src/app/**` importing `features/*/api/**`                                                                                                                                                                              | error    |
| `nothing-imports-app`          | anything outside `src/app/` importing `src/app/**`                                                                                                                                                                      | error    |
| `nothing-imports-legacy`       | anything outside the legacy set importing a module inside it; legacy importing legacy is allowed. Today's imports are a baseline that may only shrink, see "Migration notes"                                            | error    |
| `no-circular`                  | import cycles                                                                                                                                                                                                           | error    |
| `no-orphans`                   | modules nothing imports: only 1 known and accepted, measured on 2026-10-05, `lib/utils/pagination.ts`. It was 2 until #184 gave `shared/http/refresh.ts` its caller, and 3 on 2026-08-22, see "Clan capabilities" below | **warn** |

The exit code is the count of error-level violations, so one error returns 1. Warnings do
not fail the build.

**What is convention, not a gate.** The permitted direction of imports — `api` reaching
`domain`/`shared/http`/`generated`, `hooks`/`server`/`model` reaching their own `api` plus
`shared/**`, `ui` reaching its own `hooks`/`model`, `app/**` reaching `features/*/index.ts`
— is architecture, not a rule. Nothing stops you importing `shared/telemetry` from a
`model`. Follow it anyway; the rules above only catch the directions that were worth the
cost of encoding.

`src/shared/` is `http/`, `supabase/`, `telemetry/`, `testing/` and `ui/`. `shared/supabase/`
arrived with #184 (2026-10-05): `client.ts`, `server.ts` and `config.ts` moved there from
`lib/supabase/`, because `shared/http` imported them and `shared` importing `lib/` pointed the
dependency the wrong way (ADR-061 § 1). `shared/ui/` arrived with #172
(2026-10-04) and holds one file, `InitialsAvatar.tsx`: the initials circle that used to be
`components/members/MemberAvatar.tsx`, a misfiled primitive under ADR-060 § 1. A pending account
renders it directly, and `PersonAvatar` is built on it. `src/components/ui/` still holds the other
reusable presentational components, and whether they move is still a sub-project B decision that
has not been made.

**The legacy trees are in the graph, and only `nothing-imports-legacy` takes one as its subject.**
The set is the web architecture spec's § 3.2 list: `src/lib/api/`, `src/lib/hooks/`,
`src/lib/types/`, `src/application/`, `src/infrastructure/`, `src/types/`, and
`src/components/<feature>/` for `admin`, `auth`, `backoffice`, `documents`, `events`,
`family-tree` and `members`. Nothing else under `src/` is legacy: not `src/components/ui/`,
`src/components/layout/` or `src/components/providers.tsx`, and not the rest of `src/lib/`. Legacy
is cruised like any other code, so an import out of legacy is a real edge. Every rule whose `from`
could match a legacy path names `LEGACY` in `pathNot` (`nothing-imports-app`, `no-circular`,
`no-orphans`; the others only match `src/domain`, `src/features` or `src/app`), and `no-circular`
also skips an edge that ends inside legacy. **A new rule with a broad `from` needs the same.**
Legacy is being deleted, not refactored into compliance. What follows from that:

- A cycle wholly inside legacy is silent, and so is a legacy module nothing imports.
- A cycle that passes through legacy is still reported, on its edges outside legacy. Filtering on
  the cycle with `viaOnly` was rejected: dependency-cruiser records one cycle per edge, the first
  its depth-first search finds (`getCycle` in `src/graph-utl/indexed-module-graph.mjs`), so a route
  through legacy could hide a real cycle outside it.
- A module only legacy imports is not an orphan. Putting legacy in `doNotFollow` instead, so that
  legacy modules are leaves, was tried and rejected for this: once
  `lib/utils/kinship.ts` re-pointed its one legacy import, it read as an orphan, because its only
  importer, `components/family-tree/RelationshipPath.tsx`, had no outgoing edges.
- Measured 2026-10-04, `pnpm depcruise` on `main`'s config and on this one reports the same two
  `no-orphans` warnings, `shared/http/refresh.ts` and `lib/utils/pagination.ts`, and nothing else
  besides the 32 baselined `nothing-imports-legacy` edges (21 since #183). With no exclusion and no `pathNot` at
  all, legacy raises nothing either, so the guards above protect against future edits only.
  Re-measured 2026-10-05 after #184: one warning, `lib/utils/pagination.ts`, and the same 21
  baselined edges. After #185 the same day: the same one warning and 19 edges, because persons'
  two routes stopped importing the legacy capability hook. After #186: the same one warning and
  18 edges, because `lib/server/auth-context.ts`, which imported `lib/types`, is deleted.

**`api-layer-has-no-react` was vacuous from the day it was written, on every package
manager, and the first persons slice (2026-08-22) is what found it.** `to.path` in dependency-cruiser
matches a dependency's _resolved file path_
(`node_modules/dependency-cruiser/src/validate/matchers.mjs`, `matchesToPath` →
`pDependency.resolved`), never the bare import specifier. The rule's original `to.path`
was `'^(react|react-dom|@tanstack/react-query)$'` — an exact-match anchor against a
string that can never equal a resolved path, because a resolved npm import is always a
file: `node_modules/react/index.js` under plain npm, or
`node_modules/.pnpm/react@19.2.8/node_modules/react/index.js` under pnpm. Proved by
planting `import { useState } from 'react'` in a throwaway `features/persons/api/` file:
`pnpm depcruise` reported zero violations, and `--output-type json` marked that edge
`"valid": true`. Fixed to `'node_modules/(react|react-dom|@tanstack/react-query)/'`
(unanchored, matching the trailing `node_modules/<pkg>/` segment every resolver
produces), replanted the same import, and got `error api-layer-has-no-react:
src/features/persons/api/persons-api.ts → node_modules/.pnpm/react@19.2.8/...` by name.
**If you add a `to.path` rule against an npm package name, match the resolved-path shape
above, not the specifier** — the anchored form compiles, lints clean, and silently
protects nothing.

`cross-feature-only-via-index` was checked the same way and does fire correctly: a
throwaway `features/relationships/probe.ts` importing
`../persons/model/person-dto` (not through `persons/index.ts`) produced `error
cross-feature-only-via-index: src/features/relationships/probe.ts →
src/features/persons/model/person-dto.ts`. Both throwaway files were removed after the
check; neither reached a commit.

### The `persons` slice — the pattern the first slice set (`src/features/persons/{model,api}`)

**This is the first slice built on the spine alone, so read this before copying its
shape into `relationships`, `tree`, `events`, `documents`, or `admin`.**

- **`model/` holds one zod schema per wire shape, matching the generated type's
  optionality and nullability _exactly_** — not a defensively widened version of it.
  `person-dto.ts`'s own header comment explains why: each schema's inferred type is
  checked against `src/generated/api-types.ts` by a function whose body is nothing but
  `return dto`, for example `assertPersonResponseDtoMatchesGenerated`. That function only
  compiles while the DTO type stays assignable to the generated one, so **a backend
  contract change that adds a required field, removes one, or changes a type fails
  `pnpm type-check` at that function** — not at runtime, and not in a test that could be
  skipped. Verified 2026-08-22 by changing `gender: z.enum(GENDERS)` to `z.number()`:
  `tsc` failed at the assert function's `return dto` line and separately at the mapper's
  assignment into the domain `Gender` type, naming both. Widening a field (e.g. adding
  `.nullable()` where the contract does not) breaks the same check in the same way — it
  is not a safety margin, it is a lie about the contract.
- **Each DTO's mapper (`toPerson`, `toPersonSearchHit`, `toPersonActionResult`) turns
  wire `snake_case` into domain `camelCase` and normalises "key absent" into "value
  null"** — `historical-date-dto.ts`'s `toHistoricalDateOrNull` is the one place that
  does it for dates, per `historical-date.ts`'s own doc comment that the domain type
  should only ever think about one absent value.
- **`api/` returns `Promise<unknown>` from every function — the raw enveloped body,
  unparsed.** `unwrapData`/`unwrapPage` plus the model schema and mapper are composed by
  the caller — `server/persons-repository.ts`, covered below. This is
  deliberate, not a placeholder: it is what lets `api-layer-has-no-react` mean something,
  and it is what `server/` is _for_ — "fetch → parse → map to domain" in
  `web/CLAUDE.md`'s own Architecture section names three separate steps, and this slice
  is proof they run in three separate places.
- **`domain/person/person.ts` is plain TypeScript with no functions, only types** —
  `Person`, `PersonSearchHit`, `PersonActionResult`, and the `Gender` union sourced from
  `backend/app/schemas/person.py:37`'s regex, not invented. There was nothing to test:
  a type declaration has no behaviour to assert on.
- **`historical-date-dto.ts` is deliberately duplicated the day a second feature needs
  it, not factored out pre-emptively.** Every future date-bearing slice (marriages,
  events, tree nodes) parses the identical wire `HistoricalDate` object, but
  `src/domain/` cannot hold a zod schema (`domain-is-pure`) and `src/shared/` is today
  only `http/`, `telemetry/`, and `testing/` — adding a `shared/` subtree is a structural
  decision this seed did not make alone. **Copy the file rather than importing it
  cross-feature** (`cross-feature-only-via-index` would refuse the import anyway), and
  whoever copies it a _second_ time should turn the duplication into a real `shared/`
  module instead of shipping a third copy.
- **Write DTOs skip zod on purpose.** `PersonCreateRequest`/`PersonUpdateRequest` are
  typed straight from `components['schemas'][...]` in `persons-api.ts` — no zod schema
  validates them, because the caller constructs them and TypeScript already checks the
  shape at the call site. Zod DTOs in `model/` exist to validate _untrusted_ data arriving
  over the wire; an outgoing request body is not that.
- **Excluded on purpose:** the `/persons/{id}/{marriages,parent-child,documents,events,
timeline,claim}` sub-resources. Their payloads (`MarriageResponse`,
  `ParentChildResponse`, …) belong to the relationships, documents, events, and claims
  slices, not to this one, even though the route is nested under `/persons`.
- **Tests:** `model/person-dto.test.ts` feeds each mapper a full fixture (the
  `HistoricalDate` half taken verbatim from `docs/contracts/README.md`'s own example) and
  asserts on the _mapped output values_, not on schema shape. `api/persons-api.test.ts`
  exercises `listPersons`/`getPerson`/`searchPersons` against a mocked `fetchImpl`
  (`vi.fn<FetchLike>()`, same convention as `api-client.test.ts`) and covers the three
  things the slice names: the `{"data": ...}` envelope, `Page<T>` via `unwrapPage`, and a
  `400 invalid_cursor` surfacing as `ApiError` with that `code`. All three have a proven
  negative control: breaking the mapper's `fullName` field, dropping the list query
  params, and swallowing the transport error each failed the named test for that reason,
  then were reverted.

### The `persons` repository, query keys, and hooks (`server/`, `hooks/`)

**`server/persons-repository.ts` is the fetch → parse → map step the `api/` layer left open.** Every
function takes the `PersonsApiCallOptions` that layer already defined
(`context`, `signal`, `refreshAuth`, `fetchImpl`, `timeoutMs`) and returns a domain type —
`Person`, `Page<Person>`, `PersonSearchHit[]`, `PersonBatchResult`, or `PersonActionResult`
— never a DTO and never the raw `Promise<unknown>` `api/` hands back.

- **The cursor rule lives here, not in a hook.** `listPersons` catches a `400
invalid_cursor` `ApiError` and retries once with `cursor: null` before it ever reaches a
  caller. Doing it in `server/` rather than `hooks/` means the retry is testable without
  React (`persons-repository.test.ts`, no MSW, no `renderHook`) and means a screen cannot
  forget to handle it — there is nothing left for a screen to handle. It only retries when
  the failed request actually carried a cursor, so a genuinely malformed request (a 422,
  say) still surfaces as itself rather than looping.
- **The 401/403 split is proven through the repository, not reimplemented in it.**
  `apiFetch` already refreshes once on 401 and never on 403; what was still unproven is
  that two _concurrent_ repository calls sharing one `refreshAuth` (built with
  `createSingleFlight`, `shared/http/refresh.ts`) collapse onto one refresh rather than
  each calling it independently. `persons-repository.test.ts` proves it by calling
  `getPerson` twice concurrently with a shared, deliberately slow-to-resolve
  `refreshAuth`, and asserting the underlying refresh operation ran once. The real browser
  `refreshAuth` arrived with #184: `createSingleFlight` over Supabase's `refreshSession()`, one
  per tab, in `shared/http/context.client.ts` (see "One browser request context" below). A hook
  here still only forwards whatever `refreshAuth` its caller passes in.
- **`batchGetPersons` gets its own small envelope reader rather than reusing
  `unwrapPage`.** `POST /persons/batch`'s `meta` is `{errors: BatchError[]}`, not the
  cursor triplet `unwrapPage` requires, so forcing it through `unwrapPage` would mean
  faking a `has_more`/`limit` that do not exist on the wire. `items` and `errors` are
  read and mapped separately and never merged — `docs/contracts/rest-persons-api.md` is
  explicit that an unresolved id is never mixed into `data`, and `PersonBatchResult`
  (`domain/person/person.ts`) keeps that shape in the return type too.
- **The `HistoricalDate` DTO stays duplicated — the repository is not the second slice that needs
  it.** `historical-date-dto.ts` is `persons`-local on purpose until a second _feature_ (marriages,
  events, tree nodes) needs the same wire shape. The repository adds no new feature and no new wire
  shape; it is the same slice consuming what `model/` already parses.
  Nothing here changed about that file.
- **Write bodies still carry no zod validation, and that call still holds.**
  `createPerson`/`updatePerson` take `PersonCreateRequest`/`PersonUpdateRequest` typed
  straight from `components['schemas'][...]`, the same as `api/persons-api.ts` already
  did. The reasoning holds up under one direct test:
  `persons-repository.test.ts`'s "forwards a body with an unrecognised key untouched"
  sends a body carrying a key no generated type declares and asserts it reaches
  `JSON.stringify` unchanged — proof nothing runs a schema over it, not just an assertion
  that the decision is fine in prose. (Verified as a negative control too: inserting a
  real zod `.parse()` ahead of the transport call, the same key gets silently stripped
  and this test is what catches it — see the commit message.)

**Query keys live in one place, `server/query-keys.ts`'s `personsKeys`, so a read and its
invalidation cannot drift apart.** Every key is `[..., clanId, ...]`-scoped first, matching
the shape `shared/http/clan-switch.test.tsx` already proved for a plain `useQuery`: a key
built from the active clan refetches the moment `writeClanCookie` changes it, with no
manual invalidation step for a clan switch. `list`/`search`/`detail` all drop the cursor
from the key on purpose — the cursor is `useInfiniteQuery`'s own `pageParam`, identifying
_which page_, not _which list_; keying on it would turn every page into its own cache
entry that never invalidates together.

**Hooks (`hooks/use-persons-queries.ts`, `hooks/use-person-mutations.ts`) take a
`RequestContext` the caller passes in — they do not call `getClientRequestContext()`
themselves.** A screen gets the context and the `refreshAuth` to pass beside it from
`useClientRequestContext()` (#184, see "One browser request context" below). This keeps
every hook testable with a plain `RequestContext` object and MSW, which is what
`hooks/*.test.tsx` do.

- **Mutation invalidation is same-feature only, and deliberately so.**
  `useCreatePerson` invalidates `personsKeys.lists(clanId)`; `useUpdatePerson`,
  `useDeletePerson`, and `useRestorePerson` invalidate the one `personsKeys.detail(...)`
  plus every list. None of them touch `['tree']` the way the legacy
  `src/lib/hooks/query-invalidation.ts` does for the same mutations — cross-feature
  invalidation arrives with the second feature slice that needs to invalidate `persons`
  from outside it.
- **The public surface changed shape.** Before the repository landed, `index.ts` re-exported the raw
  `api/persons-api.ts` functions (`Promise<unknown>`) because nothing else existed to be
  the entry point. Now that `server/` parses, those raw functions are **no longer
  re-exported** — `index.ts` hands out the parsed repository functions and the hooks
  under the same names (`getPerson`, `listPersons`, …) instead, so a caller outside this
  feature can no longer reach the unparsed transport at all. `api/persons-api.ts` itself
  is unchanged; it is just no longer part of what `cross-feature-only-via-index` lets
  another feature see.
- **Tests:** `server/persons-repository.test.ts` (unit, `fetchImpl`-mocked, no MSW) covers
  every mapped value for every operation, the cursor-drop retry and its passthrough
  counterpart, and the 401/403 split, each with a run-and-reverted negative control (see
  the commit message for every one, with its failing output).
  `server/persons-repository.two-runtimes.test.tsx` is the real version of the stand-in
  `shared/http/context.test.tsx` already flagged as temporary: it calls `getPerson` once
  through `getServerRequestContext()` and once through `getClientRequestContext()` against
  the same MSW-mocked backend and asserts the two resulting `Person` values are equal —
  `.tsx`, not `.ts`, because `getClientRequestContext` needs `document.cookie`, which only
  exists under the `component` project's jsdom environment; a node-environment version
  would make "both runtimes agree" true for the wrong reason (every browser-side read
  would resolve to null). `hooks/*.test.tsx` cover the query/mutation wiring itself:
  loading → success → error for `usePerson`, cursor pagination for `usePersonsList`
  without ever parsing the cursor, disabled-when-blank for `usePersonSearch`, and — with
  its own negative control — that a successful `useCreatePerson` mutation makes an
  already-mounted `usePersonsList` refetch with no re-render or manual `refetch()` call.

**`pnpm depcruise` coverage was checked, not assumed.** No rule in `.dependency-cruiser.cjs`
names `server/` or `hooks/` specifically — only `api/` (`api-layer-has-no-react`) and `ui/`
(`ui-does-not-call-transport`) get a directory-specific rule. `cross-feature-only-via-index`
is written path-agnostically (`^src/features/([^/]+)/` with no subdirectory name), so it
already covers every subdirectory including these two. Proved by planting
`src/features/relationships/probe.ts` importing `../persons/server/query-keys` directly,
then `../persons/hooks/use-persons-queries` directly: both produced
`error cross-feature-only-via-index: src/features/relationships/probe.ts → ...` by name,
`pnpm depcruise` went from 0 errors to 1, and both throwaway files were removed afterward,
neither reaching a commit. `depcruise` stayed at **0 errors, 3 warnings** before and after
that batch's real changes — the same three orphans already recorded above, unaffected,
since `refresh.ts` is still imported only from `.test.ts` files, which the graph excludes.

### The persons create/edit form and its `409 stale_write` dialog (`ui/PersonForm.tsx`)

**The repository's return shape changed.** `createPerson`/`updatePerson` (`server/persons-repository.ts`)
now resolve `PersonWriteResult` (`{ person, warning }`, `@/domain/person/person`), not a bare
`Person` — spec §7.7a's "`meta.warning` on a successful write ... the save succeeds, and a
`warning` toast appears afterwards" needs the envelope's `meta.warning`, which `unwrapData`
never returns (it hands back `data` only). A new `readWriteWarning` reads `raw.meta.warning`
straight off the same raw body `unwrapData` already parses, the same shape `batchGetPersons`
uses for its own `meta.errors`. `hooks/use-person-mutations.ts` needed no logic change —
`mutate`/`mutateAsync` just resolve to the wider type now — but its own doc comments say so,
and `server/persons-repository.test.ts` gained a case with a run negative control: reverting
`readWriteWarning`'s call site back to a bare `unwrapData(raw, parsePerson)` makes the new
`createPerson surfaces meta.warning` test fail with `undefined` where a string was expected.

**The `409 stale_write` path is the reason this seed exists, and it is not a generic error
banner.** `PersonForm.tsx`'s `onSubmit` catches an `ApiError` with `code === 'stale_write'`,
refetches the record (`getPerson`, this feature's own `server/`, not a hook — `ui/` may reach
its own `server/`; only `ui-does-not-call-transport` restricts `api/`), diffs it against the
form's current values (`stale-write-diff.ts`'s `diffPersonFormValues`), and opens
`StaleWriteDialog` with one row per field that actually differs, spec §7.7c. A row's default
choice is "keep mine" when the user actually edited that field since the form loaded, "use
latest" otherwise — a real three-way comparison (loaded / typed / latest), not a two-way one,
and `stale-write-diff.test.ts` has a negative control proving the naive two-way reading (which
would default every row to "mine", since every row's `mine` differs from `latest` by
construction of the filter) fails the case where the user never touched the field.

**`PersonForm.test.tsx`'s own conflict test carries the negative control this seed's
instructions asked for, run by hand and reverted.** With the `onSubmit` branch's
`error.code === STALE_WRITE_CODE` check changed to `false`, "opens the field-level conflict
dialog instead of a generic error banner" fails: the `waitFor` on "Người khác vừa sửa hồ sơ
này" times out because the 409 falls through to the generic `setSubmitError` branch instead —
the exact silent-loss shape this seed exists to prevent. Reverted, and the suite is green
again. See the commit message for the actual failing output.

**First use of `@radix-ui/react-dialog` in `web/src`** (`.claude/rules/tailwind.md` §4: the
package was installed and imported by no file before this). `StaleWriteDialog` and
`ForbiddenWriteDialog` (the 403-mid-edit case, same spec paragraph) both control `Dialog.Root`
from the caller's own `open` state and call `event.preventDefault()` in `onEscapeKeyDown` and
`onInteractOutside`, matching spec §7.7c's "not dismissible by scrim tap" literally rather than
by convention.

**A real browser measurement found and fixed a genuine `T-04` defect before this seed closed,
not after.** `StaleWriteDialog`'s field-comparison rows originally laid "Bản của bạn" / value
side by side in a `flex items-baseline justify-between` row. Measured 2026-08-22 at 320px width
with `:root { font-size: 32px }` (200%) against a throwaway preview route (`StaleWriteDialog`
rendered directly with fixture rows, no backend, deleted before this commit): the dialog's own
`clientWidth` was 250px against a `scrollWidth` of 288px — a real 38px overflow invisible at
the _document_ level (`documentElement.scrollWidth === clientWidth === 320` the whole time)
because Radix's `overflow-y-auto` on `Dialog.Content` computes `overflow-x` to `auto` too, per
the CSS spec's rule for a box with one axis scrolling and the other `visible` — so the overflow
became an invisible _internal_ horizontal scroll rather than a page-level one. The cause was the
classic flexbox `min-width: auto` trap: a flex item's implicit minimum width is its own longest
unbroken content run, so the value span refused to wrap. Fixed by stacking label above value
(a block layout has no such minimum) instead of the spec diagram's side-by-side line, and by
adding `flex-wrap` to the segmented mine/latest button row, which had the identical defect at
106px available width against two buttons wanting ~215px combined. Re-measured after the fix:
`dialog.clientWidth === dialog.scrollWidth` (250 === 250) at 320px/200%, and again with no
overflow at 1280px/200%. Screenshots were taken and reviewed, then discarded; the two width
readings above are what was verified this way.

**Scope this change deliberately did not cover, named rather than left silent:**

- Fields shown are exactly spec §7.7's own list. `religion`, `nationality`, `occupation`,
  `educationLevel`, `titleRank`, `phone`, and `email` exist on `Person` but are not in that
  list; `nationality` is sent as the backend's own default `'VN'` on create since the field
  is required there regardless. `phone`/`email` additionally carry ADR-049's role-narrower
  write rule (a `viewer` may write them only on their own linked person), which this form does
  not attempt to gate — a reason beyond the spec's own silence to leave both out for now.
- "Chi/nhánh" (spec §7.7's field list) has no home: `Person` carries no branch field at all,
  the same finding `ui/PersonRow.tsx`'s own comment already recorded for the list row.
- The success/warning "toast" is an inline confirmation panel inside `PersonForm.tsx` that
  replaces the form until the user continues, not a cross-navigation global toast — no toast
  primitive exists anywhere in this codebase (`app/[locale]/(dashboard)/members/page.tsx`'s own
  comment calls inventing one "exactly the kind of write-UX decision" a seed should not make as
  a side effect of something else). This seed is the one that had to decide, and decided
  narrowly, confined to this one component.
- The unsaved-changes guard covers the in-form Cancel button (a `window.confirm`) and a real
  tab close/reload (`beforeunload`), not in-app navigation through the page shell's own back
  link — the App Router has no `routeChangeStart`-equivalent to intercept that without a custom
  `Link` wrapper.
- A second `409` on the resolved resubmit reopens the dialog with fresh data and a
  `repeatedConflict` note (spec §7.7c's own text), proven in `person-form-schema.ts`'s design
  and wired in `PersonForm.tsx`, but has no dedicated component test — `PersonForm.test.tsx`
  covers the first conflict, the resolve-and-save path, and the discard-and-reload path, not
  the repeat.

### The spine (`src/shared/http/`, `src/shared/telemetry/`, `src/domain/date/`)

- `apiFetch` (`src/shared/http/api-client.ts`) is the **only** way to reach the backend.
  It attaches `Authorization`, `Accept-Language`, `X-Current-Clan-Id`, and a `traceparent`;
  applies a timeout via `AbortSignal.timeout`; and distinguishes a caller-initiated abort
  from a transport failure. **On the server it sends to `API_URL` when that is set** (ADR-056,
  since #186), read per request, because inside compose's `web` container the browser's
  `localhost` is the container itself. Unset, both runtimes use `NEXT_PUBLIC_API_ORIGIN`.
- Request context (`RequestContext`) is always **passed in**, never read from a global —
  `context.server.ts` builds it from `cookies()` + Supabase SSR in an RSC,
  `context.client.ts` builds it from the `current_clan_id` cookie, the URL and the Supabase
  browser client. A client component reads it through `useClientRequestContext()`. The same
  repository function runs, and is tested, in both runtimes.
- `unwrapData` / `unwrapPage` (`src/shared/http/envelope.ts`) are the **only** readers of
  the `{"data": ...}` / `{"data": ..., "meta": {...}}` envelope. No component ever sees the
  wrapped shape. `unwrapPage` rejects the pre-envelope `{data, next_cursor, has_more}` shape
  outright. Cursors are opaque — never parsed or constructed; on `400 invalid_cursor`, drop
  the cursor and refetch page one.
- The UI branches on the error **`code`**, never on `message` — `message` arrives already
  localized from the backend (`src/shared/http/errors.ts`, `ApiError` / `NetworkError` /
  `MalformedResponseError`).
- 401 triggers a single-flight refresh-then-retry (`src/shared/http/refresh.ts`, wired to
  Supabase as `refreshAuth` in `context.client.ts`); 403 never refreshes, because it is a
  policy decision, not a stale credential.
- `HistoricalDate` (`src/domain/date/historical-date.ts`) owns its own render rule (`date`
  when `precision === 'exact'`, else `display`, falling back to `date`); no component
  re-implements it.

### One browser request context (`useClientRequestContext`, #184)

**ADR-061 § 6, built by #184.** A slice's client component reads its context from
`useClientRequestContext()` in `shared/http/context.client.ts`, and passes `context` and
`refreshAuth` to its slice's hooks. It returns `{ context, ready, refreshAuth }`. Persons'
`use-persons-request-context.ts` and invitations' `use-invitation-request-context.ts`, which each
read the token once on mount and passed no `refreshAuth`, are deleted.

**The legacy slices are the exception.** `infrastructure/{admin,documents,events,relationships,tree}`
still call the backend through `lib/api/axios.ts`, whose interceptor signs out and redirects on a
401 instead of refreshing. They gain the refresh when their own slice PR moves them onto `apiFetch`.

- **The token follows Supabase.** The hook reads `getSession()` once and then every
  `onAuthStateChange` event, so a `TOKEN_REFRESHED` from Supabase's own timer or from
  `refreshAuth` reaches the next request with no remount. An event that lands first wins over the
  first read, which may be older. The access token is not in any query key, and need not be:
  TanStack Query runs the latest render's `queryFn`.
- **`refreshAuth` is one per tab.** The module-level export is `createSingleFlight` over
  `refreshSession()`, so concurrent 401s from every caller of it share one refresh. It resolves
  the refreshed context, or `null` when Supabase refuses, and then `apiFetch` surfaces the 401.
  `refreshAuthFor(clanId)` wraps it so a retry carries the clan its first attempt carried; the
  hook's own `refreshAuth` is that wrapper.
- **`ready` gates the request.** It is false until the first session read finishes, so no call
  goes out without the `Authorization` header a signed-in user has. A Supabase client that cannot
  be built reads as signed out rather than leaving `ready` false.
- **`clanScoped: false` sends no `X-Current-Clan-Id`**, on the first attempt or the retry. The
  invitee surface uses it, because its contract forbids the header. The auth slice's
  `authCallOptions()` passes `refreshAuthFor(null)` for the same rule, since its callers are a
  query function and callbacks, not components.

`src/shared/http/use-client-request-context.test.tsx` holds the two outcomes the issue named, each
seen to fail against its planted defect on 2026-10-05. Two persons queries in two components, both
401ing on the old token, cause one `refreshSession()` and both retry with the new one; built per
hook call instead, the count was 2. A `TOKEN_REFRESHED` reaches the next request's `Authorization`;
with the token read once on mount, the old token went out. Two more cases there pin the first-read
guard and the unbuildable client. `PersonsList.test.tsx`, `InvitationAcceptScreen.test.tsx` and
`use-session.test.tsx` each pin that their screen refreshes, and the last two that the retry
carries no clan.

### Routing, locales, auth gating

- next-intl with locales `vi | en | zh | fr`, **default `vi`**, `localePrefix: 'always'` — every route is prefixed (`/vi/...`, `/en/...`). See `src/i18n/routing.ts` and `messages/*.json`.
- Route groups under `src/app/[locale]/`: `(auth)` (login/register/callback/pending-approval — public), `(dashboard)` (protected), plus `backoffice/`, `platform/`, `select-clan/`.
- **Three layers route a signed-in user, and only the middle one decides (#186, ADR-061 § 3).**
  1. **`src/middleware.ts`** checks only that a Supabase session exists and, on a clan-scoped
     route, that the `current_clan_id` cookie parses. It calls no backend. Detail below.
  2. **The server guard** makes every other routing decision.
     `guardClanRoute(locale, capability?)` and `guardPlatformRoute(locale)` live in
     `features/auth/server/guard.ts` and reach `app/` through `@/features/auth/index.server`, a
     second public entry, because `index.ts` is imported by client components and the guard is
     `server-only`. It reads the
     session (`GET /auth/me` and `GET /me/clans`, once per request through React `cache`) and the
     cookie, computes `accessStateOf` (the function `useSession` uses), and redirects by
     `clanRouteDecision` / `platformRouteDecision` in `features/auth/model/route-guard.ts`: every
     state that is not ready goes where `landingPath` sends it; a clan route that names a
     capability sends a member without it to `/{locale}/dashboard`; a cookie naming a clan the
     user is not in goes to `/{locale}/select-clan`, whose picker rewrites it; a platform route
     admits `platform_role` `super_admin` only. A failed session read throws, for
     `app/[locale]/error.tsx`, and is never read as an access state.
  3. **Client components only render.** `Sidebar`, `Header` and `DashboardShell` read the
     session through `useSession` and redirect nowhere. The one exception left is
     `SelectClanScreen`, which still routes a state it cannot serve through `landingPath`.
- **Who calls the guard.** The `(dashboard)` layout, with no capability. `admin/users/layout.tsx`
  with `viewPendingUsers`, `admin/clan/layout.tsx` with `editClanSettings`: those pages are client
  components, so each guards in a layout of its own, and `admin/layout.tsx` guards nothing.
  `backoffice/layout.tsx` with `viewPendingUsers`. `platform/layout.tsx` through
  `guardPlatformRoute`. Persons' `members/page.tsx` and `members/[id]/page.tsx` call it for the
  capabilities, the active clan and the request context (its token, with the active clan as
  `X-Current-Clan-Id`), which costs no second session read. **A super_admin has no clan bypass**:
  one without an admin membership in the active clan is turned away from `admin/` and
  `backoffice/`, as the backend would refuse them the endpoints those pages call.
- **Each request now spends a server-side `GET /auth/me`** on top of the browser's one from
  `useSession`. Both come from the same address in the e2e harness, so mind its rate limit.
- **What pins it, each seen to fail against its plant on 2026-10-05.**
  `features/auth/model/route-guard.test.ts` holds the table: with the `platform_role` branch
  dropped from `accessStateOf`, the platform row fails; with the capability never checked, four
  capability cases fail; with a stale cookie admitted, its case fails.
  `features/auth/server/guard.test.ts` runs one request through the real repository against MSW
  and records every request sent: a `/platform/metrics` probe put back fails the three request
  cases, naming `GET /api/v1/platform/metrics`; the session read sent with the clan header fails
  the header case; a failed read swallowed into "signed out" fails the error case. "No probe" is
  read there, not in an e2e network log, because the guard's requests leave the Next server.
  `e2e/auth/guard.auth.spec.ts` holds the browser readings; its header names each plant.
- `src/middleware.ts` runs the intl middleware first, strips the locale prefix, lets `PUBLIC_ROUTES` through, and for everything else creates a Supabase SSR client (`@supabase/ssr`) and redirects to `/<locale>/login` when there is no session. If Supabase env vars are missing the auth check is skipped — be aware in local dev.
- **After the session check, `src/middleware.ts` gates `CLAN_SCOPED_SEGMENTS` (`dashboard`, `documents`, `events`, `members`, `tree`, `admin` — everything under the `(dashboard)` route group) on the `current_clan_id` cookie.** Missing and unparseable (not a UUID) are the same case, both read as "no clan selected" through `parseClanCookie` (`src/shared/http/request-context.ts`), and both redirect to `/<locale>/select-clan` rather than letting the route render and fire a clan-scoped `apiFetch` call with no `X-Current-Clan-Id`. `platform/*`, `backoffice/*`, and `select-clan` itself are deliberately not gated: `platform/*` is a cross-clan super-admin surface (`docs/architecture/multi-tenancy.md`), and gating the picker page would loop. `backoffice/*` is clan-scoped, and its guard asks for `viewPendingUsers` in the active clan (#186); with no cookie, a user holding one membership acts in it, and one holding several is sent to the picker by the guard rather than by the middleware. `middleware.ts`'s own comment still calls both cross-clan. See `web/src/middleware.test.ts`.

### Every string goes through next-intl (#194)

- **The rule.** Every string a person reads or hears goes through next-intl, with a real
  translation in all four locale files, not a copy of the English. That covers visible text, an
  `aria-label`, a `placeholder`, a `title`, an `alt`, and an `<option>`. A Vietnamese literal is the
  direction no review catches: it reads correctly on `/vi/...` and shows Vietnamese to every
  English, Chinese and French reader. `messages/message-key-parity.test.ts` holds the four key sets
  equal. It cannot tell whether a component uses them.
- **Reuse a key before adding one**, where an existing key says the same thing in all four locales.
  A second key for one sentence is a second place for it to drift (S-092, `0d2cf15`). The visible
  wording may move to the existing key's. #194's three such moves: the header's placeholder option
  reads `invitation.continue_button`, so English went from "Select clan" to "Choose a clan"; the
  platform clan list's loading line reads `common.loading`, "Đang tải…" to "Đang tải..."; and its
  status reads `platform.inactive`, "Tạm ngưng" to "Không hoạt động".
- **Four classes are not copy**, and may stay literal in source:
  1. Numerals and example values. `placeholder="1750"` reads the same in every locale.
  2. Language endonyms. `LocaleSwitcher.tsx`'s `Tiếng Việt`, `English`, `中文` and `Français`: each
     language names itself, so a reader finds their own whatever the current locale is.
  3. Punctuation and emoji glyphs: `:`, `*`, `(`, `)`, `_`, `👑`. A glyph is no language's word,
     so it reads the same to every reader.
  4. Developer-facing error text that is never rendered, such as a thrown `Error`'s message.
- **A not-copy word carries a one-line comment at its site**, naming its class and the reason:
  `// Not copy: an example year, a numeral that reads the same in all four locales.` A glyph or
  an error string needs none, because its class shows on the line. The comment is how the next
  count tells a considered line from a missed one.
- **Re-take the count; do not reconstruct it.** From `web/`:

  ```bash
  # (a) JSX text
  ./node_modules/.bin/eslint --no-cache --rule '{"react/jsx-no-literals": "error"}' 'src/**/*.tsx' --ignore-pattern '**/*.test.tsx'
  # (b) literal attributes
  grep -rnE '(aria-label|placeholder|title|alt)="[^"{]+"' src --include='*.tsx' | grep -v '\.test\.tsx:'
  # (c) literal branches of a JSX ternary
  grep -rnE "\? [^?]*: '[^']*[[:alpha:]][^']*'\}" src --include='*.tsx' | grep -v '\.test\.tsx:'
  # (d) object properties
  grep -rnE "\b(label|title|description|change)\s*:\s*'[^']*[[:alpha:]]" src --include='*.ts' --include='*.tsx' | grep -vE '\.test\.tsx?:|src/generated/'
  ```

  Each has a blind spot. (a) reports the line a text node starts on, which for text on a line of
  its own is the line above the word. (c) also prints `className` ternaries. (d)'s `[[:alpha:]]`
  does not match CJK in the C locale, so `中文` is found only by reading the file. On 2026-10-06,
  after #194, the four printed 17, 2, 3 and 15 lines. Every hit was a commented site, a glyph, a
  `className` ternary, a line #197 holds (the product name, the auth screens #183 moved into
  `features/auth/ui/`, and `backoffice/dashboard/page.tsx`'s mock stats), or `app/layout.tsx:36-37`,
  the root `metadata`, which #197 leaves alone because every routed page's `[locale]` metadata
  overrides it and no person reads it.

- **`react/jsx-no-literals` is not in the gate.** It sees JSX text only, so it misses every ternary
  and object property above. A partial guard is a change to the gate and needs its own decision.
- **Formatting is not covered by any of this.** `EventCalendar.tsx` passes `{ locale: vi }` to
  date-fns, and `lib/utils/date.ts` defaults to `'vi'`, so month names are Vietnamese for every
  reader. That is a formatting defect, not a literal, and none of the four commands finds it.
- **How to test a swept string.** Render under a locale whose value is not the literal (`en` for a
  Vietnamese literal, `vi` or `zh` for an English one), with the real locale file, and read what a
  person gets: `getByText`, `getByRole(…, { name })`, or `toHaveAccessibleName` for an
  `aria-label`, never the attribute. Wrap each expected value in `expected()` from
  `src/shared/testing/render.tsx`, which throws on a missing key: `toHaveAccessibleName(undefined)`
  degrades to "has some name", and the old literal passes that. For an async server component,
  mock its guard, await the element it returns, and stand next-intl's `createTranslator` over the
  real file in for `getTranslations` (`app/[locale]/platform/layout.test.tsx`).

### The `current_clan_id` cookie

The cookie is the single source for the active clan: `context.server.ts` reads it through
`cookies()`, `context.client.ts` reads the identical value through `document.cookie`, and
both run it through the same `parseClanCookie` (`src/shared/http/request-context.ts`) so a
Server Component and a browser session never disagree about which clan is active. A
`localStorage`-only value (the legacy path's third fallback) is invisible to a Server
Component, which is the whole reason this moved to a cookie.

**Attributes, decided once in `context.client.ts` so every later slice inherits them rather than
re-deciding:**

| Attribute  | Value                                      | Why                                                                                                                                                                                                                                                                                                                                                                                        |
| ---------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `httpOnly` | not set (false)                            | Forced, not chosen: `context.client.ts` reads the cookie through `document.cookie`, and a script that can read a cookie can set it, so declaring `httpOnly` would be theatre. The cookie is also not a credential — the backend re-validates it against the caller's actual memberships on every request (`get_current_clan_id`) — so nothing sensitive leaks by it being script-readable. |
| `sameSite` | `lax`                                      | Sent on a normal top-level navigation, withheld on a cross-site subrequest or form post — the standard mitigation for a script-writable cookie. Matches the legacy writer, `src/infrastructure/auth/clan-selection-storage.ts`.                                                                                                                                                            |
| `secure`   | only when `location.protocol === 'https:'` | `document.cookie` silently drops a hard-coded `Secure` attribute set from an insecure origin rather than erroring, which would break local `http://localhost` dev instead of protecting anything.                                                                                                                                                                                          |
| `path`     | `/`                                        | Every locale-prefixed route reads it, and so does `src/middleware.ts`, which runs before any narrower path is known.                                                                                                                                                                                                                                                                       |
| `max-age`  | one year                                   | A UI preference the backend re-validates, not a session credential — no security reason to expire it sooner.                                                                                                                                                                                                                                                                               |

`parseClanCookie` treats the value as unparseable unless it matches the UUID shape every
`clan_id` takes in the backend (cast `::uuid` throughout `docs/architecture/data-model.md`),
and returns `null` rather than forwarding garbage as `X-Current-Clan-Id`.

**The cookie is now the only writer too.** Since #183 three places write it, each through
`writeClanCookie` / `clearClanCookie`: `useAuthActions().selectClan`, and a sign-in or onboarding
that lands a user ready in one clan. The `(dashboard)` layout was a third until #186, when the
cookie named a clan the user had left; the server guard now sends that case to the picker, whose
`selectClan` writes it. Sign-out clears it. Before #183 the legacy `useAuth`'s `selectClan` and
`syncAuthContext` did. The legacy `persistCurrentClanId` / `clearCurrentClanId`
(`src/infrastructure/auth/clan-selection-storage.ts`) are unused now — nothing imports
them — because they also wrote `localStorage.current_clan_id`, which the cookie rule forbids. The
file was left in place rather than deleted at the time: deleting the legacy auth transport was its
own change, and `pnpm depcruise`'s `no-orphans` check is a warning, not a gate, so an unused legacy
file cost nothing until that deletion ran.

**No `features/` repository exists yet to write a cross-runtime test against** (`src/features/`
lands with the first feature slices). `src/shared/http/context.test.tsx` proves the closest thing that
exists today: `getServerRequestContext` and `getClientRequestContext` resolve the same
`clanId` for one cookie, and a bare `apiFetch` call — what a repository function does under the
hood — carries the identical `X-Current-Clan-Id` from both. Read the file's own comment before
assuming a later slice's repository test can copy this shape verbatim; it is a stand-in, not the
real pattern.

### Clan capabilities (`src/domain/capability`)

`src/domain/capability/capability.ts` maps each clan role (`admin`, `editor`, `viewer`) to the
`CapabilitySet` it holds, taken from `docs/architecture/rbac.md`'s permission matrix — one capability
per matrix row where at least one role is denied, each cited to its row in a doc comment. It is pure:
no React, no store, no `apiFetch`, enforced by `domain-is-pure` and `domain-imports-only-domain`.
**The backend still enforces the real check on every request**; this module only decides what the
client offers to render.

**Do not replace the table with a role-hierarchy comparison, even though every row looks nested.**
`docs/architecture/rbac.md:106` gives `editor` ✅ for deleting an event, while `:98` and `:85` give
`editor` ❌ for deleting a relationship and a person. The nesting is empirical, not guaranteed, and a
hierarchy shortcut would hide that.

**The server guard reads the same mapping (#186).** `capabilitiesOf(role)` in
`features/auth/model/capabilities.ts` turns a membership role into the `CapabilitySet`, every key
false for a role that is not one of the three. `useCapabilities()` and the guard both call it, so a
screen and the route guarding it cannot disagree about a role.

**The client reads it through `useCapabilities()` from `@/features/auth` (#185, ADR-061 § 4).**
The hook (`features/auth/hooks/use-capabilities.ts`) returns the domain `CapabilitySet` for the
active clan's membership role from `useSession()`. It returns `NO_CAPABILITIES`, every key false,
when there is no session, no active clan, or a role that is not one of the three (`asClanRole`).
The rows these names come from are `docs/architecture/rbac.md:84` (`editPerson`) and `:101-102`
(`uploadDocument`, `deleteDocument`). **The `rbac.md:NN` citations in `capability.ts` itself are
about 28 lines stale**, measured 2026-10-05: they predate rows added above the matrix. Read the
row by its title, not its number, until they are corrected.
Callers read the domain names: the persons create and edit routes gate on `editPerson`,
`DocumentUpload` on `uploadDocument`, and `DocumentGallery` on `deleteDocument`. The four renamed
booleans the legacy hook in `lib/hooks/` returned are gone, and so is that hook. A caller that
needs another capability reads it off the same set. Do not add a named boolean beside it.

**Every capability is also false while the session loads**, so a gated screen shows its denied
state until the session lands. A test of a denied case must therefore wait for the session to
settle on the role before it reads, or it passes whatever role arrives. The three tests that pin
the hook do: `features/auth/hooks/use-capabilities.test.tsx`, `members/new/page.test.tsx` and
`components/documents/documents-capabilities.test.tsx`, all through the real session hook with MSW
serving `/me/clans`. Each was seen to fail on 2026-10-05 against its planted defect. A set that is
all true failed the viewer case on `members/new`. `deleteDocument` mapped from `uploadDocument`
failed the editor case on the documents components. A viewer read as an editor failed both viewer
cases, which is what shows the wait is real.

**`editor` deletes events.** `deleteEvent` follows `docs/architecture/rbac.md:106`, which grants
`editor`, unlike person, relationship and document deletion. The legacy module deleted on
2026-08-22 hardcoded it admin-only. No screen reads `deleteEvent` yet. When one does, the wider
grant is the correct one.

**Why `no-orphans` once counted `capability.ts`.** Until #171 (2026-10-04), `LEGACY` sat in
`options.exclude`, so the legacy hook that consumed this module drew no edge, and `capability.ts`
read as an orphan on 2026-08-22. #171 put legacy back in the graph, and by then
`domain/invitation/invitation.ts` imported the module anyway. `features/auth` imports it too now.

### The session is one query (`src/features/auth`, #183)

**ADR-061 § 2, built by #183.** `store/auth.store.ts` and `lib/hooks/useAuth.ts` are deleted, with
`application/auth/`, `infrastructure/auth/`, `components/auth/` and `lib/hooks/useClanContext.ts`.
zustand keeps only `ui.store.ts`.

- **The session is one TanStack Query query**, `useSession()` (`features/auth/hooks/use-session.ts`),
  over `GET /auth/me` and `GET /me/clans`, fetched through `apiFetch` and parsed in
  `server/auth-repository.ts`. Every consumer reads the one cache entry `authKeys.session()` names,
  so the request count does not grow with the number of components that ask: one `GET /auth/me`
  per `/vi/dashboard` load, measured 2026-10-04, against 9037 before (finding 2 below). The key
  carries no clan id, because the session says who is signed in and never which clan they act in.
- **Nothing persists it.** Nothing writes the user, the role or the memberships to
  `localStorage`, and the first consumer to mount removes the `localStorage['auth-store']` entry a
  browser kept from the old app. `use-session.test.tsx` reads both.
- **Supabase's `onAuthStateChange` resets it, through one subscription per query client**, however
  many consumers mount: the first subscribes and the last to unmount lets go. `SIGNED_OUT` sets the
  session to none with no request. `SIGNED_IN` and `USER_UPDATED` invalidate it, which keeps the
  current value on screen while it refetches, because Supabase also sends `SIGNED_IN` when a tab
  becomes visible again and a reset there would flash every screen to its loading state.
- **Where a user belongs is one pure function**, `accessStateOf(session, cookieClanId)` in
  `src/domain/session/access-state.ts`: signed out, pending approval, needs onboarding, needs clan
  selection, platform, or ready in an active clan. It replaces both copies of
  `resolveCurrentClanId`, which disagreed: the client's fell back to the profile's `clan_id` and
  the server's did not. `activeClanOf` in the same file is the one clan resolution. Since #186
  the server guard calls `accessStateOf` itself ("Routing, locales, auth gating"). `access-state.test.ts`
  has one case per row, and deleting any branch fails its row (run 2026-10-04).
- **`landingPath(access, locale)`** (`model/landing.ts`) is the one table from a state to a route.
  Sign-in, onboarding, the blocked-state screens and the `(dashboard)` layout all route through it.
  A super_admin with no membership lands on `/platform/clans`.
- **The actions are `useAuthActions()`**: sign in with email, Google or Apple, sign out, register,
  onboard, select clan. They read no session through `useSession`, so a sign-out button adds no
  consumer. Sign-in stays Supabase-direct (ADR-061 § 7), and a password sign-in Supabase refuses
  with `email_not_confirmed` routes to `/{locale}/verify-email?email=…`. Routing uses the URL's
  locale; the legacy hook used the profile's `preferred_locale`.
- **The slice builds its own request context, the one exception to "hooks take a
  `RequestContext` the caller passes in".** The session is where the identity behind every other
  context comes from, so nothing above it holds one to pass. `authCallOptions()` in
  `hooks/auth-request-context.ts` reads `getClientRequestContext()` per call with no
  `X-Current-Clan-Id`, since no auth route is clan-scoped, and passes the shared browser
  `refreshAuth` with the same rule (#184, ADR-061 § 6).
- **`useSession()` returns `activeClan`** beside `access`: the membership the user acts in when
  the state is ready, `null` otherwise. `Header`, `Sidebar`, `SelectClanScreen` and
  `useCapabilities` read it rather than each testing `access.kind`.
- **The screens live in `features/auth/ui/`**: `LoginScreen`, `RegisterScreen`,
  `SelectClanScreen`, `PendingApprovalScreen`, `ClanSuspendedScreen`, `VerifyEmailScreen` and
  `SupabaseSetupNotice`. Their `app/` pages only route.
- **Three interim adaptations, each replaced by a later issue.** ~~The `(dashboard)` layout keeps a
  client redirect, driven by the access state, and writes a ready user's active clan back to the
  cookie when the cookie names another.~~ #186 made it a server layout that calls the guard; the
  guard sends a cookie naming a clan the user is not in to the picker instead. The legacy capability hook
  read the role from the session and kept its four names, until #185 replaced it with the slice's
  own `useCapabilities()` (see "Clan capabilities"). The legacy
  `infrastructure/http/request-context.ts` reads the clan from the cookie only and the locale from
  the URL; its `useAuthStore` fallback and its `localStorage['preferred_locale']` read are gone.
  The issue said nothing writes that key any more. That was wrong: `ui.store`'s `setLocale` still
  writes it, from `LocaleSwitcher`. The legacy `useAuth` was the other writer. Nothing reads it
  now.

**The one reactive read of the active clan is still `useCurrentClanId()`**
(`src/shared/http/context.client.ts`), a `useSyncExternalStore` over the `current_clan_id` cookie
that `writeClanCookie` and `clearClanCookie` notify. `useSession` derives the access state from it
on every render, so a clan switch re-derives every consumer's state with no refetch of the session,
and a TanStack Query key built from the clan id refetches without a page reload
(`src/shared/http/clan-switch.test.tsx`). `readCurrentClanId()` is the one-shot read for a caller
that is not a component, such as the sign-in action.

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
from `getRequestContext()` (`src/infrastructure/http/request-context.ts`), which reads the
`current_clan_id` cookie only, and the locale from the URL, since #183. SSR returns a minimal
context (`{ locale: 'vi' }`). Do not extend this path — it is being deleted by the slice PRs.

**The legacy-transport deletion (2026-08-22) tried to remove `axios.ts`, `src/lib/api/auth.ts`, and
`src/infrastructure/http/request-context.ts` outright, and could only close two of the three.** It
named all three, plus the auth halves of `application/auth` and `infrastructure/auth`, as this
repository's "no PR only adds" rule applied to PR 1. Enumerating
every importer first (`grep -rln "lib/api/axios\|from 'axios'" src`, 2026-08-22) found `axios.ts`
imported not just by the auth infrastructure but by `src/infrastructure/admin/http-admin-repositories.ts`
(four live pages: `platform/clans`, `platform/metrics`, `admin/users`, `admin/clan`) and, through
`src/lib/api/{documents,events,members,relationships,tree}.ts`, by every other legacy slice's
repositories too. `request-context.ts` backs `axios.ts` the same way for all of them. Deleting
either would have broken the persons, tree, events, documents, and admin halves that were meant to
stay until their own slice PR — `axios.ts` is the legacy app's one
shared transport, not an auth-only file, and this file's own "Migration notes" section already
said so before that deletion ran; its own plan did not cross-reference it. **What actually left:**
`src/lib/api/auth.ts` (`authApi`, dead — its sole in-code match on `grep -rn "lib/api/auth" src`
was a comment quoting a grep command, not an import) and
`src/infrastructure/auth/clan-selection-storage.ts` (dead per the auth-store section above). **What stays, and
why it is not a smaller version of "done":** `application/auth/ports/auth-repository.ts`,
`application/auth/use-cases/auth-context.ts`, `infrastructure/auth/http-auth-profile-repository.ts`,
and `infrastructure/auth/supabase-auth-session-port.ts` are the live implementation
`useAuth()`'s session sync, sign-in redirect, onboarding, and clan selection call today — deleting
them needs a spine replacement (`apiFetch` calls where `http-auth-profile-repository.ts` calls
`axios.ts`) that does not exist yet, since `src/features/auth/` has not landed. Building that
replacement as a side effect of a deletion seed would be a materially larger, differently-tested
change than "delete legacy code with a live-behind replacement", so it was left as future work
rather than rewritten under a deletion's name. `axios.ts` and `request-context.ts` leave only
when the last legacy slice PR (persons, tree, events, documents, admin, and then auth's own
transport) replaces its own repository, per this section's existing rule that they are "being
deleted by the slice PRs" — plural, and not yet all landed. **#183 deleted the four auth files
named above** once `features/auth` replaced them; `axios.ts` and `request-context.ts` remain.

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
- **Client state**: Zustand — `src/store/ui.store.ts` only. The session is server state, one
  TanStack Query query (see "The session is one query" above), and the active clan is
  `useCurrentClanId()` over the `current_clan_id` cookie.
- Forms: react-hook-form + zod resolvers.

### UI

Tailwind + Radix primitives. Reusable primitives in `src/components/ui/` and `src/shared/ui/` (see "Dependency rules"); feature components in `src/components/<feature>/`. Mind the Arbor Heritage design mandates referenced in the repo-root `CLAUDE.md`.

### Testing

Four harnesses, one gate each:

- `pnpm test:unit` — Vitest, node environment, `*.test.ts` under `src/`. Pure domain and
  `shared/http` logic: `HistoricalDate`, envelope unwrapping, the error taxonomy, request
  context, trace id generation, single-flight refresh, `apiFetch`, the logger. `vitest.config.mts`
  adds four globs outside `src/`, each with its reason: `messages/**`, `e2e/**/*.guard.test.ts`,
  `scripts/**`, which holds the legacy gate's test, and `playwright.config.test.ts`, which reads
  whether an e2e run uses a server it did not start (#192).
- `pnpm test:component` — Vitest, jsdom, `*.test.tsx`. React Testing Library + MSW
  (`src/shared/testing/`); MSW handlers build real envelopes, so a test cannot invent a
  response shape.
- `pnpm test:e2e`: Playwright (`web/playwright.config.ts`, `web/e2e/`). Boots its own `next dev`
  on `:3100`, and the banner spec's on `:3101`, unless `E2E_PORT_BASE` moves them. Runs desktop
  Chrome and a Pixel 5 viewport. **Eight specs, counted on disk
  2026-08-27**, and `CI=1 pnpm test:e2e` reported `106 passed` the same day. This said "Four
  specs" until then and was already undercounting by one at the batch base — `git ls-tree
e9a8809:web/e2e/` returns five — so re-count with `ls web/e2e/*.spec.ts` rather than trusting a
  prose figure. The earlier "36 tests on 2026-08-21" reading is left as written, because it
  carries its own date. The four described below are the original set; `supabase-banner.spec.ts`
  `register-clan-code.spec.ts`, `register-join-code.spec.ts`, and `invitation-accept.spec.ts` are
  the other four:
  - `smoke.spec.ts` — locale redirect, the login form renders, and (since the fix to
    `R-lang`, see `docs/sad/11-risks-and-technical-debt.md`) `<html lang>` tracks the route
    locale on both `/vi/login` and `/en/login`.
  - `fonts.spec.ts` — the two mandated typefaces reach the screen. A computed
    style in a real browser is the only thing that can see a dead `font-family`.
  - `text-scale.spec.ts` — `T-04`: no horizontal page scroll at 320 px width and 200% root
    font size. jsdom has no layout engine, so no other harness can measure a box.
  - `dark-theme.spec.ts` — the dark palette reaches `body` under an emulated dark colour
    scheme, and no class or attribute is involved (ADR-045). The stylesheet holds
    both palettes and cannot tell you which one won the cascade; only an engine can.

  These cover what only a browser can measure, and every spec in this list runs against public
  routes. Authenticated routes are the section below.

- `pnpm test:e2e:auth` — the authenticated projects, off by default. See "The authenticated
  e2e harness" below. `pnpm test:e2e` does not run them and must never need Docker.

- `tests/behavior/` (legacy) — Node test runner with `--experimental-strip-types` for `.ts`.
  Focused on auth + query invalidation flows against the legacy trees; not part of the CI
  gate for new code.
- `tests/contracts/` (legacy) — `.mjs` contract tests that pin the legacy API client shapes.

CI (`.github/workflows/web-ci.yml`) runs type-check, lint, `depcruise`, the legacy ratchet on pull
requests, unit, component,
build, e2e, and `api-types-fresh` (regenerates `src/generated/api-types.ts` from the
backend's OpenAPI schema and fails the build if it drifts — the anti-R3 gate). The
freshness job is triggered by changes under either `web/**` or `backend/app/**`, so a
backend-only PR that changes response shapes cannot skip it.

`.github/workflows/image-e2e.yml` (#193) builds the web image with its three `NEXT_PUBLIC_*`
build arguments, reads its `/vi/login` in Chromium for the missing-Supabase banner, and runs
`pnpm test:e2e:auth` against the built backend image. `docs/ops/local-supabase.md`, "The image e2e
job in CI".

## Two worktrees, one machine (#192)

**An e2e run only measures dev servers it started.** This is the web counterpart of the backend's
`TEST_PG_DB_NAME` (`backend/CLAUDE.md`, "Running two suites at once"; ADR-016), and it is worse in
one way: two backend suites sharing a database fail loudly, and a port collision did not. Before
#192 all three `webServer` entries set `reuseExistingServer: !process.env.CI`, so outside CI a run
that found its URL already answering used that server and started nothing. On 2026-08-26 an agent's
second run resolved `:3100` to a `next dev` whose working directory was another seed's worktree. It
reported 48 passed and 10 failed, and the failures were `ERR_CONNECTION_REFUSED` only because the
other worktree's servers shut down partway. Had they stayed up, it would have reported a pass.

- **By default a busy port fails the run.** Each entry starts its own server, and if its URL
  already answers, the run stops before any spec with Playwright's own message:
  `http://127.0.0.1:3100 is already used, make sure that nothing is running on the port/url or set
reuseExistingServer:true in config.webServer.` Ignore the last clause. Setting it in the config
  is the defect this closed. Use one of the two variables below instead.
- **`E2E_PORT_BASE` moves all three ports**, to base, base+1 and base+2. Unset, they are 3100
  (hermetic), 3101 (banner) and 3102 (authenticated). `BASE_URL`, `BANNER_BASE_URL` and
  `AUTH_BASE_URL` follow it, and so must the backend's `CORS_ORIGINS` and `INVITE_LINK_ORIGIN` in
  the authenticated recipe below, which compute the auth origin from it. Every parallel web
  dispatch that runs the e2e gate sets its own, at least three apart, for example
  `E2E_PORT_BASE=3110` and `E2E_PORT_BASE=3120`. A value that is not a whole number from 1024 to
  65533 fails the run, naming the variable and the value. A hash of the worktree path was rejected:
  two hashes can collide, and the auth origin has to be predictable for `CORS_ORIGINS`.
- **`E2E_REUSE_SERVER=1` attaches**, to whatever already answers on each URL, as-is and with
  whatever env it was started with. It covers all three ports at once, so a server you meant to
  reuse, such as a warm `:3102` (the authenticated harness's cold-compile trap, below), brings
  whatever else answers on :3100 and :3101 with it. Check every port before you set it. Under `CI`
  a run never attaches, whatever this says.
- **Who holds a port:** `lsof -nP -iTCP:3100 -sTCP:LISTEN` prints the listening PID, then
  `lsof -a -p <pid> -d cwd` prints its working directory, which names the checkout. Read it for
  every port a run uses before you trust a reading from it. **On Linux with lsof 4.99.4 the first
  command prints nothing while the port is held** (measured 2026-10-05). Next 16's listener is a
  child named `next-server (v16.2.12)`, and that lsof skips any process whose name has a
  parenthesis: a probe socket named `probe-srv (v1` was invisible to it and one named
  `probe-srv-v1` was not. There, read the PID with `ss -ltnp 'sport = :3100'`, then
  `readlink /proc/<pid>/cwd`, or `lsof -a -p <ppid> -d cwd` on its parent `next dev`
  (`ps -o ppid= -p <pid>`).
- **Do not broad-`pkill` a dev server you did not start.** `pkill -f "next dev"` kills every
  worktree's servers, another agent's mid-run included, and that run then fails with
  `ERR_CONNECTION_REFUSED` for a reason in neither checkout. Stop only a PID whose working
  directory, read as in the bullet above, is your own checkout.
- **Why CI never caught it.** Under `CI` the old setting was already false, so in CI the defect
  did not exist. It lived only on developer machines and agent worktrees, where nothing gates.
- **What this does not make safe.** Two **authenticated** runs side by side still share one
  Supabase stack, one seeded database, the backend `E2E_AUTH_API_ORIGIN` names, and that backend's
  20-per-60-seconds limit on `/api/v1/auth` per IP. That collision fails loudly with 429s rather
  than passing, and it is out of #192's scope: run `pnpm test:e2e:auth` one at a time.

**`playwright.config.test.ts` holds it in the unit gate.** Two stand-in servers hold base and
base+1, the way another worktree's `next dev` would, and record every path asked of them. Each case
runs the real `playwright test` with a wrapper config that spreads the real one and changes only
`testDir`, to a throwaway spec that requests one path through the `request` fixture, so no browser
is needed. It reads which server the spec reached, not the setting: with nothing set the run fails
naming `http://127.0.0.1:<base>` and the stand-in never sees the spec's path; with
`E2E_REUSE_SERVER=1` it does; under `CI=1` with the opt-in, it does not; and `E2E_PORT_BASE=31OO`
fails naming the value. Every case removes `CI` from the run but the one that sets it, because
under `CI` the old config never attached either. Each case was seen to fail on 2026-10-05 against
its plant: the old `!process.env.CI` fails the first, the opt-in honoured under `CI` fails the
third, reuse never on fails the second, a literal hermetic or banner port fails the cases that
reach it, and no validation fails the last, on `TypeError: Invalid URL`.

**The issue's four readings with two worktrees, 2026-10-05.** Reading 3 has two halves, 3a and
3b. A and B were worktrees of this repository. The plant was `lang="en"` for `lang={locale}` in
`src/app/layout.tsx`, which fails `smoke.spec.ts`'s "declares Vietnamese" case with
`Received: "en"`. Every port was attributed while specs ran, with the `ss` form above.

| Reading                                                                   | B's result                                           | B's ports resolved to    |
| ------------------------------------------------------------------------- | ---------------------------------------------------- | ------------------------ |
| 1. `main` in both, A planted and serving 3100/3101, B clean, nothing set  | 104 passed, 2 failed, both `Received: "en"`          | A                        |
| 2. this fix in both, the same servers, nothing set                        | `http://127.0.0.1:3100 is already used`, no spec ran | A (held), B started none |
| 3a. B `E2E_PORT_BASE=3200`, clean, A still planted                        | 106 passed                                           | B on 3200/3201           |
| 3b. the plant moved: A clean and serving, B planted, `E2E_PORT_BASE=3200` | both smoke cases `Received: "en"`                    | B on 3200/3201           |
| 4. A planted, B clean, `E2E_REUSE_SERVER=1`, no base                      | 104 passed, 2 failed, both `Received: "en"`          | A, by request            |

Two runs with B on 3200, the first try at reading 3a and reading 3b, also failed one case the
plant does not touch: `invitation-accept.spec.ts`'s "no request the page makes carries the token in
a Referer header", once in `chromium` and once in `mobile`, reading B's own
`http://127.0.0.1:3200/vi/invitations/<token>`. Alone, on B's cold servers at 3200, it passed four
of four. It is intermittent under a full run's load and not explained yet. Reading 3a's pass above is
the rerun. The gate's own `pnpm test:e2e` in the primary checkout, at the default ports with nothing
else listening, failed once the same day: 86 passed and 20 failed, every one of them
`invitation-accept.spec.ts`, every page Next's own 404. The spec passed ten of ten alone, and the
full suite rerun reported 106 passed. Also not explained. With nothing listening, the old and new
configs start the same servers, so neither failure reads on this change.

## The authenticated e2e harness (2026-08-26)

**One command, and it is not part of `pnpm test:e2e`:**

```bash
# preconditions, from the repository root — see docs/ops/local-supabase.md and
# docs/ops/seed-test-users.md
docker compose up -d pgdb
scripts/supabase_local.sh up
make seed                                  # both halves of five test users

# a backend that trusts the LOCAL stack, and whose CORS admits the auth origin in use:
# base+2 of E2E_PORT_BASE, which is :3102 when it is unset ("Two worktrees, one machine").
# Set E2E_PORT_BASE to the same value, or leave it unset, in this shell and in web/'s.
# `docker compose up api` does not do this: its `environment:` sets neither CORS_ORIGINS
# nor INVITE_LINK_ORIGIN, so it runs on config.py's http://localhost:3000 defaults, which
# admit no auth origin (read at source 2026-10-05). The harness only needs some backend on
# E2E_AUTH_API_ORIGIN that admits it.
AUTH_ORIGIN="http://127.0.0.1:$(( ${E2E_PORT_BASE:-3100} + 2 ))"
cd backend && DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/family_roots \
  SUPABASE_URL=http://supabase.localhost:54321 \
  SUPABASE_ANON_KEY=... SUPABASE_SERVICE_ROLE_KEY=...  \
  CORS_ORIGINS="[\"$AUTH_ORIGIN\"]" INVITE_LINK_ORIGIN="$AUTH_ORIGIN" \
  APP_SECRET_KEY=e2e-local-secret \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8073

# then, in web/
export E2E_AUTH_STACK=1
export E2E_AUTH_SUPABASE_URL=http://supabase.localhost:54321   # NOT the 127.0.0.1 form
export E2E_AUTH_SUPABASE_ANON_KEY="$(scripts/supabase_local.sh env | ...)"
export E2E_AUTH_API_ORIGIN=http://127.0.0.1:8073
pnpm test:e2e:auth
```

**CI runs the same command against the built backend image** (`image-e2e.yml`, #193). Its backend
values differ from the recipe above, `INVITE_LINK_ORIGIN` most of all. `docs/ops/local-supabase.md`,
"The image e2e job in CI", lists each one and why.

**Twenty-one tests as written on 2026-10-05 (#191)**: three `auth-setup` logins and eighteen
`auth-chromium` cases. #191 added `invitation-link.auth.spec.ts`'s three, which call the backend
directly and so need it started with `INVITE_LINK_ORIGIN` as above. Two traps the first full run
on a machine with Docker hit that day, neither from #191's cases. **A cold `next dev` compiles a
route in about 18 seconds**, so the three setup logins, which each wait 30, timed out on a fresh
server; a second run, reusing the warm `:3102` server outside CI, passed them. Since #192 a run
reuses a server only under `E2E_REUSE_SERVER=1`, and that variable reuses **every** port the run
uses, :3100 and :3101 included, which `backoffice.auth.spec.ts`'s replay reads. So before running
with it, check that each port is free or held by your own checkout ("Who holds a port"). On
2026-10-05 the setup logins passed cold without it. **The full run
spends the 20-per-minute bucket**: the server guard's `GET /auth/me` met a 429 (`Quá nhiều yêu
cầu`) and `guard.auth.spec.ts`'s super_admin case read `500` where it expects `307`.
**Eighteen tests as written on 2026-10-05 (#186)**: three `auth-setup` logins and fifteen
`auth-chromium` cases. #186 added the super_admin's login and `guard.auth.spec.ts`'s five, and
was written on a machine without Docker, so its pull request says whether they have been run.
Before #186, **twelve tests, 2026-10-04**: two `auth-setup` logins and ten `auth-chromium` cases. #183 added
`dashboard.auth.spec.ts`'s two. It was ten earlier that day, and nine on 2026-08-26, one of them a
deliberate `test.fail()` over an open T-04 defect; #174 fixed the defect and replaced that case
with two that read the fix (finding 3, below).

### What holds the session, and why there is no stub

`e2e/auth/session.setup.ts` types a seeded user's real password into `/vi/login`, presses the
button, waits for the sign-in to land on `/vi/dashboard`, checks the `sb-…-auth-token` cookie
`@supabase/ssr` writes, and saves the context with `storageState()` into `e2e/.auth/`
(git-ignored — those files are live credentials). Until #183 it polled for the cookie and left at
once, because the dashboard ran away (finding 2). `e2e/auth/backoffice.auth.spec.ts` and
`dashboard.auth.spec.ts` then load a state file per `test.describe`.

**The seeded users** are `fixtures.ts`'s `SEEDED_USERS`: `admin` and `viewer` in `nguyen-phuc`,
and since #186 `superAdmin`, `platform_role` `super_admin` with no membership. Its capture in
`session.setup.ts` does not read where the sign-in lands, so a defect in `accessStateOf` fails a
case in `guard.auth.spec.ts` instead of the setup every case depends on.

**Nothing under `src/` participates.** That is the fence, and it is a mechanism rather than a
promise:

1. **There is no switch to flip.** `playwright.config.ts` and `e2e/` are not imported by
   anything under `src/`, so `pnpm build` never compiles them. A production request has no
   code path — no env var, no header, no flag — that yields a session it did not earn,
   because no such path exists to reach.
2. **`e2e/auth/no-session-bypass.guard.test.ts` keeps it that way.** It runs under
   `pnpm test:unit` (`vitest.config.mts` includes `e2e/**/*.guard.test.ts`) and fails if any
   file under `src/` mentions `E2E_*`, `PLAYWRIGHT`, `storageState`, or `e2e/.auth`, or
   imports from `e2e/`. **Proved not vacuous on 2026-08-26**: planting
   `if (process.env.E2E_AUTH_STACK === '1') return { … }` at the top of
   `getServerAuthContext` (the legacy guard #186 deleted) produced
   `AssertionError: expected [ 'src/lib/server/auth-context.ts' ] to deeply equal []`,
   naming the file. Removed; the suite went back to 434 passing.
3. **The credential is worthless elsewhere.** `backoffice.auth.spec.ts`'s last case replays
   the captured admin state against the hermetic server (`BASE_URL`, `:3100` by default), which
   points at `https://e2e-fake-project.example.supabase.co`, and reads `307 → /vi/login`. Cookies are
   named for their project (`sb-<ref>-auth-token`) and the token is signed by the stack that
   issued it. **This does not prove middleware checks a signature — it does not**;
   `supabase.auth.getSession()` reads the cookie. Signature checking is the backend's JWKS
   flow (`backend/app/core/security.py`), which is that layer's guarantee, not this one's.

`E2E_AUTH_STACK=1` gates the projects _and_ the third `next dev` (`:3102` by default). Absent,
neither exists, so `pnpm test:e2e` keeps its guarantee: no Docker, no network, same answer in a
fresh clone, in a worktree, and in CI. Present but under-configured, `authStackEnv()` throws
naming the missing variables — deliberately not a skip, because a suite that quietly covers
nothing when Docker is down is the "passed because it scanned nothing" failure
`.claude/rules/testing.md` warns about.

### How to add the next authenticated route

1. **Pick a route whose gate is server-side.** Add a case to
   `e2e/auth/backoffice.auth.spec.ts`, or a new `e2e/auth/<name>.auth.spec.ts` — the
   `auth-chromium` project's `testMatch` picks up `e2e/auth/*.auth.spec.ts` with no config
   change. Reuse `SEEDED_USERS.admin.storageState` via `test.use({ storageState })`.
2. **Assert a role-dependent outcome, not the presence of markup.** One URL read with two
   sessions is the assertion that only a real session can produce. `page.request.get(path, {
maxRedirects: 0 })` reads a server-side gate as a status and a `Location` without
   mounting anything, which costs no renders and cannot be confused by a client effect.
3. **Give both Locations.** A viewer refused by the server guard for want of a capability gets
   `307 → /vi/dashboard`; a request with no session gets `307 → /vi/login`. If your two
   readings are the same string, you have a control that reads the same either way, which is no
   control at all.
4. **Read colour schemes without reloading.** `page.emulateMedia({ colorScheme })`
   re-evaluates the media query in place, and ADR-045 made the media query the only
   mechanism. One page load per case matters: see the rate limit below.
5. **Budget the requests.** `/api/v1/auth/*` allows 20 requests per 60 seconds per IP
   (`backend/app/main.py:221-226`, hardcoded). One load of a `(dashboard)` screen spends two
   `GET /auth/me` since #186: the server guard's, and the browser's one, which every consumer
   shares since #183. Both come from `127.0.0.1` here. It was about three per load, and then
   thousands, before #183. Keep a case to one navigation.
   `dashboard.auth.spec.ts` counts the browser's alone, which is why it still reads 1.
6. **The backend has to be current.** `GET /auth/me` sends `platform_role` since #181, and the
   session's schema requires it. A backend started before #181 merged answers without it, and every
   sign-in then fails on the login screen with the zod error naming `platform_role`. Seen
   2026-10-04, against a backend on `:8073` started that morning.

### Three things found by looking at the harness

All three are fixed: 1 by #182, 2 by #183 and 3 by #174, all on 2026-10-04. Each is marked fixed
rather than deleted, so it keeps its history.

**1. `GET /me/clans` and `POST /me/clans/{id}/select` were read as unenveloped, and both are now
fixed.** The web client read `{"clans": […]}` and `{clan_id: …}` while the backend has
always answered `{"data": …}` (`backend/app/api/v1/me.py:25,36`;
`Envelope_list_UserClanMembership__` at `src/generated/api-types.ts:2192-2196`;
`docs/contracts/frontend-integration-guide.md:77`). The first left `currentClanRole`
permanently `undefined`, so **every role-gated element on every server-rendered screen was
hidden and `requireServerRole` sent approved admins to `/pending-approval`**. The second wrote
the literal string `undefined` into the `current_clan_id` cookie. Both read sites are now
unwrapped in `HttpAuthProfileRepository`, which is the one place the port's shape is built —
see the doc comments there. **`register` and `onboard` in that same file had the identical
defect, and #182 fixed both (2026-10-04).** They were once said to be covered by the
invitation-accept work; that was stale, corrected 2026-08-27, because that work's 27-file diff
never touched this file.

**What the `register` half cost, as it was read at source 2026-08-27:** `http-auth-profile-repository.ts:81` is
`api.post<RegisterResult>('/auth/register', input)` and returns `data`, which is the whole body
`{"data": {"message": ...}}` that `backend/app/api/v1/auth.py:62` sends (`:61` until #182 corrected it). So `result.message` is
`undefined`, `setSuccess(undefined)` leaves `success` falsy, and the `if (success)` branch never
renders — **a successful registration showed the user nothing.** No test caught it, because
`register/page.test.tsx` mocks `useAuthActions`, so its `signUp` resolves whatever the test hands
it.

**The fix and what holds it.** Both methods now return `data.data`, and the port types `register`
as `RegistrationReceived` (`{ message }`, the `MessageData` the route sends) rather than the
onboard shape. `register/page.success.test.tsx` mocks only `next/navigation`: the real
`useAuthActions` and repository run against MSW serving the real 201 envelope, and the test reads
the message on screen and the form gone. It reaches nothing #183 moves, and its handler matches
any origin, so #183, which rewrites the repository onto `apiFetch`, keeps it green unchanged. It
did: unedited, it passes against #183 with the Supabase variables unset and set to placeholders.
`infrastructure/auth/http-auth-profile-repository.test.tsx` read `clan_id` off `onboard`'s result;
#183 deleted it with that repository, and `features/auth/server/auth-repository.test.ts`'s
`onboard` case reads the same value, with the fixture typed by the generated `RegisterResponse`. Negative controls, 2026-10-04:
reverting the `register` unwrap fails the first with "Unable to find an element with the text"
and no error banner on the page; reverting the `onboard` unwrap fails the second with `expected
undefined to be '4bf92f35-…'`. The two source-text assertions in
`tests/contracts/api-clients.test.mjs` that pinned the defective `api.post<RegisterResult>` calls
are deleted: they pinned a setting, per `.claude/rules/testing.md`.

**2. The `(dashboard)` group runs away, so `/vi/members` is not the covered route. Fixed by #183
(2026-10-04).** The harness's
first choice was `/vi/members`, the screen the persons and calendar work each wanted. It cannot be
read: measured 2026-08-26, `/vi/dashboard` re-ran `useAuth`'s mount effect **2613 times in
seven seconds** and issued **18174 `GET /auth/me`** until the backend's limiter answered 429.
Two `useAuth()` consumers mount on every `(dashboard)` page (`(dashboard)/layout.tsx:12` and
`Header.tsx:18`), each hydrates independently, each hydration writes three fresh objects into
the zustand store, and `syncAuthContext`'s identity does not survive that. **The loop was
invisible before**, because the envelope defect above made `hydrateAuthContext` throw on its
first call and fall into its own `catch`; fixing the envelope is what let the loop start. It
is legacy auth code and its own piece of work — do not fix it inside a feature PR. **ADR-061 § 9:**
#183 removes it by design, with no stopgap. #182 fixed the `register`/`onboard` defect above
first.

**The fix, #183.** The session is one query that every consumer shares ("The session is one
query", above), so no consumer hydrates on its own and nothing writes a store that re-renders the
others. `e2e/auth/dashboard.auth.spec.ts` loads `/vi/dashboard` as the seeded admin, waits for the
network to go idle and five seconds more, and counts `GET /auth/me`. Measured 2026-10-04:

| Build                                                          | `GET /auth/me` | Reading                                                       |
| -------------------------------------------------------------- | -------------- | ------------------------------------------------------------- |
| `main` before #183, one 12-second probe, deleted after         | 9037           | 3111 of them answered 429; the network never went idle in 7 s |
| #183                                                           | 1              |                                                               |
| #183 with `Header` reading the session under its own query key | 2              | the planted defect                                            |

The issue asked for "at most 2", with the planted defect having to cross it. It does not: two keys
send two requests, and "at most 2" passed the plant. A bound the defect it names cannot cross pins
nothing (`.claude/rules/testing.md`, question 2), so the case asserts exactly 1, and the plant
fails it with `Expected: 1, Received: 2`. The second case loads `/vi/members`: `GET /persons`
answers 200 and the list renders its empty state, since `make seed` writes no persons.

Run against a backend on `:8074` started from `main` at #181 or later; see step 6 above for why
the older one on `:8073` could not be used. The "before" probe ran against `:8073`, whose missing
`platform_role` the legacy client never read.

**3. "No horizontal page scroll" is not a usability reading, and this screen proved it. Fixed by
#174 (2026-10-04).** `e2e/text-scale.spec.ts`'s T-04 assertion passed on `/vi/backoffice/dashboard`
at 320×640 with a 32px root, while every pixel of content was outside the viewport. Measured
2026-08-26:

```
aside     x=0    width=480      // `w-60` is 15rem = 480px at a 32px root
main      x=480  width=0        // `ml-60` adds another 480px; flex-1 collapses to zero
main h1   x=544  width=0
documentElement scrollWidth 320 === clientWidth 320, overflow-x: visible on html and body
```

Zero-width content cannot be scrolled to, so the page reported no overflow. The spec kept the
scroll assertion (a reader will look for it) with a comment saying it proves almost nothing,
and pinned the real defect with `test.fail()` so a future responsive fix would turn the suite
red instead of leaving the case behind. `backoffice/layout.tsx:31-32` paired a `fixed w-60` rail
with `ml-60` and had no small-screen branch. This is a fourth instance of the pattern in
`.claude/rules/testing.md` § "A test pins an outcome, not a setting".

**The fix, #174.** Spec § 6's drawer nav, chosen over an icon rail and a stacked rail by the
#162 prototype's measurements. Below `lg` (64rem), `BackofficeSidebar` renders a top bar with a
menu button and the brand, and the rail in a `@radix-ui/react-dialog` drawer,
`min(85vw, 16.5rem)` wide, that a link, Escape and a scrim tap all close. At `lg` and up the
rail is an in-flow, `sticky` `16.5rem` sibling of `main` in one flex row, and `main` is `min-w-0 flex-1`. No
`fixed` rail is paired with an `ml-*` anywhere in the shell. The two bodies are one `RailBody`,
and the component calls `useAuth()` once for both: every consumer hydrates on mount, so a drawer
body that called it would add a `GET /auth/me` on every open, and two live consumers is finding
2's loop. Planting that call in the body made six hydration requests on one open.

Two things the prototype did not show, found by reading the drawer at 320 px and 200%:

- **The drawer's brand overlapped its close button while the drawer reported no overflow.**
  `.claude/rules/tailwind.md` § 7 has the measurement. The header now wraps the close button onto
  its own line when the two do not fit, and the drawer case reads where each line of the brand is
  inked rather than trusting `scrollWidth`.
- **The nav scrolled on its own inside the drawer**, inherited from the `lg` rail, so two of the
  four links sat below a scroll edge with nothing on screen to say so, and `toBeVisible()` passed
  over it. The rail and the drawer now each scroll as a whole. No case pins this one.

The `test.fail()` is gone. Two cases, one navigation each, read these outcomes at 320×640 with a
32px root, measured 2026-10-04: `main` 320 wide against `clientWidth` 320; `main.scrollWidth` 320
against its `clientWidth` 320; the `h1` from x 64 to 256 and y 176 to 368 (x 32 to 288 and y 176
to 304 since #175's `px-4`); the top bar's `scrollWidth` 320 against 320; and after the menu button,
the four links visible by name, the drawer's `scrollWidth` 272 against `clientWidth` 272, no line of
the brand inked across the close button, no hydration request, and a scrim tap that closes it. The
page-level scroll reading stays, with its comment, because the reason it proves nothing still holds.

**Then the page inside that column failed T-04 too, and the scroll reading passed over it again.
Fixed by #175 (2026-10-04).** Every stat value was clipped to nothing and the approvals badge sat on
its card's title, because the cards hide their overflow. The scroll reading now lives in one case
with T-04's other two clauses, on the same navigation, so the suite is still ten tests: every
heading and paragraph in `main` has width and fits it, and the badge's box meets neither the
title's box nor any line of the title as inked. `.claude/rules/tailwind.md` § 7 has the layout
chosen, the readings, the negative controls, and two traps: a transition that moves the boxes after
the scale changes, and a fix that passed in `vi` and failed in `en`.

**Two smaller findings the harness reported and did not fix. Both are fixed now, and this
paragraph is corrected rather than deleted so the finding keeps its history.**

- The login form's labels carried no `htmlFor` and its inputs no `id`. **Fixed**:
  `(auth)/login/page.tsx:93` is `<label htmlFor="login-email"` with `id="login-email"` at `:97`,
  and `htmlFor="login-password"` at `:109` with `id="login-password"` at `:115`.
- `BackofficeSidebar.tsx` hardcoded English `Sign out`, and `Sidebar.tsx:70` hardcoded Vietnamese
  in an `aria-label`. **Fixed**: the first is now `{tAuth('logout')}`, reusing the key
  that already had three callers rather than adding a fourth spelling, and the second is
  `aria-label={sidebarOpen ? t('common.collapse') : t('common.expand')}`.

**The register page had the login page's defect, in the same file as the new fields. Fixed by
#195 (2026-10-04).** Counted 2026-08-27: three labels there carried no `htmlFor` and their inputs
no `id`, while the three fields added below them by the join-code work were correct. **Fixed**:
the three take the login page's prefix, `htmlFor="register-full-name"` at
`(auth)/register/page.tsx:265` with its `id` at `:271`, `register-email` at `:281`/`:287`, and
`register-password` at `:301`/`:307`. The clan fields and the two wrapping radio labels are
unchanged. `register/page.test.tsx` reads a name or a focus, never the attribute: each label
through `getByLabelText`, every `form input` in join, create and OAuth onboarding mode (6, 7 and
5 inputs) through `toHaveAccessibleName`, and `document.activeElement` after a click on each
label. Both e2e `fillTheRest` helpers and `page.success.test.tsx` fill the three by label. Negative
control, 2026-10-04, with the attributes reverted: `getByLabelText` throws "Found a label with the
text of: Họ và tên, however no form control was found associated to that label", `form input`
0, 1 and 2 fail `toHaveAccessibleName`, focus stays on `body`, and 12 e2e cases time out "waiting
for getByLabel('Họ và tên')". jsdom and Chromium resolve the pairing; neither is a screen reader.

### The four workarounds this replaces

Four changes each built a throwaway route, screenshotted it, and deleted it before committing,
because no test could hold a session. **Use this harness instead of rebuilding one.**

| The change              | What it could not reach                                                  | What it did instead                            |
| ----------------------- | ------------------------------------------------------------------------ | ---------------------------------------------- |
| the persons list/detail | `/vi/members` with data (reachable since #183, `dashboard.auth.spec.ts`) | a throwaway route                              |
| the persons form        | the conflict dialog (`StaleWriteDialog`)                                 | a throwaway preview route                      |
| the calendar            | the calendar with data                                                   | a throwaway preview route                      |
| the ten-file conversion | none of the files on a reachable route                                   | its own verification was impossible as written |

ADR-046 is the fifth case and the one now covered directly: it could not read the
backoffice rail in a browser and said so. `backoffice.auth.spec.ts` reads that rail's `muted`
ground and its `primary` mark in both schemes, which is ADR-046's own claim measured in an
engine rather than computed from the stylesheet.

## Migration notes

- The legacy set, the web architecture spec's § 3.2 list in full under "Dependency rules" above,
  predates the envelope contract and the spine built above. It is frozen, not extended: no new
  feature should add to it. **Since #171 (2026-10-04) that is a gate, and the gate only shrinks**
  (ADR-060 § 4). `nothing-imports-legacy` forbids any module outside the set from importing one
  inside it. The imports that already existed are the baseline,
  `web/.dependency-cruiser-known-violations.json`, 32 entries on 2026-10-04, 21 after #183, 19
  after #185 and 18 after #186, which `pnpm depcruise` reads through `--ignore-known`. None of the
  18 starts in `features/auth`, and none starts in a persons route.
  - **When a slice deletes or re-points a legacy import, shrink the baseline in the same pull
    request:** run `pnpm depcruise:baseline` and commit the shorter file. Do not edit it by hand.
    `pnpm depcruise:ratchet origin/main` fails while the baseline still lists an import the tree no
    longer has, because a leftover entry would quietly re-admit that import later.
  - **The baseline may not grow.** CI runs `pnpm depcruise:ratchet` against the pull request's merge
    base and fails on any entry the merge base did not have, naming it. Regenerating the baseline
    to admit a new import makes `pnpm depcruise` pass locally and still fails there. If new code
    needs something only legacy has, the answer is the owning slice's `index.ts` (ADR-060 § 2),
    not the baseline.
  - **Use the package script, not `depcruise-baseline`.** The script writes
    `nothing-imports-legacy` entries only. dependency-cruiser's own tool also writes the
    `no-orphans` warnings, and `--ignore-known` would then hide them.
  - **What the ratchet trusts.** It compares baselines under the rule as committed. A pull request
    that edits `LEGACY` or the rule itself changes the policy, and review is the only gate on that.
  - **Proven on the outcome.** `scripts/legacy-baseline.test.ts`, in `pnpm test:unit`, builds a
    throwaway git repository with the real `.dependency-cruiser.cjs`, plants
    `import { useAuth } from '@/lib/hooks/useAuth'` in a feature, and reads what a pull request
    would see: `pnpm depcruise` fails naming the edge; with the baseline regenerated to admit it,
    the ratchet fails naming the edge; a shrink passes; a stale entry fails. It also plants each
    of the legacy cases in "Dependency rules", beside the same plant outside legacy, where the
    rule must fire.
- **How a slice deletes its legacy is ADR-060, not "the matching PR deletes it".** In short: a slice
  deletes its _slice-owned_ legacy, after re-pointing every importer, in any slice, at its own
  `index.ts`. Adapting an importer to the domain shape is part of the migration. A file stays,
  trimmed, only where `index.ts` has no replacement, and the importing slice's build issue then
  owns it. _Cross-cutting_ files go with the last slice (next bullet). A _misfiled primitive_,
  such as `components/members/MemberAvatar.tsx`, moves to `shared/ui`. A slice is done when none of
  its slice-owned legacy remains **and** it imports no legacy itself.
- **Persons applied it first (#172, 2026-10-04).** `lib/hooks/useMembers.ts`, `application/persons/`,
  `infrastructure/persons/`, `lib/api/members.ts` and `components/members/` are deleted.
  `MemberSidebar` reads `usePerson` from `@/features/persons` and renders the domain `Person`,
  `MemberNode` renders `PersonAvatar`, and `MemberAvatar` became `shared/ui/InitialsAvatar.tsx`.
  The deletion removed no baseline entry, because every importer it re-pointed sits inside legacy
  itself (`components/family-tree/`, `components/admin/`), and legacy importing legacy is not a
  violation. What is left:
  - `lib/types/member.ts` declares `PersonSummary` only, under § 2's fallback. `lib/types/tree.ts`
    embeds it and persons has no replacement for tree's wire shape, so the tree slice owns the
    file and deletes it.
  - ~~Persons' own routes still import the legacy capability hook.~~ The auth slice re-pointed
    them at `@/features/auth` in #185 (2026-10-05), per ADR-060 § 3, and the baseline lost both
    entries. ~~`members/page.tsx` and `members/[id]/page.tsx` still call `getServerAuthContext`
    from `lib/server/auth-context.ts`.~~ #186 (2026-10-05) moved both onto the server guard's
    context and deleted the file. Persons imports no auth legacy.
- **`src/lib/api/axios.ts` is one file shared by every slice above, not one file per slice.**
  The 2026-08-22 deletion went looking for it while removing the legacy auth transport and found
  `src/infrastructure/admin/http-admin-repositories.ts` and every one of
  `src/lib/api/{documents,events,members,relationships,tree}.ts` importing it too
  (`grep -rln "lib/api/axios\|from 'axios'" src`; `members.ts` has since left with persons, #172). So it, and the
  `src/infrastructure/http/request-context.ts` it depends on, cannot leave until the **last**
  slice PR lands, not the first — "each is deleted outright when the matching feature slice PR
  lands" above is true per-slice-repository-file, not true of this shared pair. See
  "Backend contract" above for the full account and what that deletion could and could not remove.
- `src/domain/` is currently `shared/` plus `date/` (the `HistoricalDate` model added by the
  spine PR). As features land, domain types move out of `src/types/` and `src/lib/types/`
  into `src/domain/<feature>/`.
- New transport code goes in `src/shared/http/` (or, once a feature slice PR lands,
  `src/features/<slice>/api/`) — never in `src/lib/api/` or `src/infrastructure/`.
- **Auth applied it second (#183, 2026-10-04).** `lib/hooks/useAuth.ts`, `lib/hooks/useClanContext.ts`,
  `store/auth.store.ts`, `application/auth/`, `infrastructure/auth/` and `components/auth/` are
  deleted, after every importer was re-pointed at `@/features/auth`: `Header`, `Sidebar`,
  `BackofficeSidebar`, the `(dashboard)` layout, the login, register and select-clan pages, the
  three blocked-state pages, and `useCapabilities`. The baseline lost 11 entries, and
  `features/auth` imports no legacy. What of auth's legacy is left, and who removes it (ADR-061 § 8):
  - ~~The capability hook in `lib/hooks/`~~: replaced by `useCapabilities()` in `features/auth`
    by #185 (2026-10-05), with the last two auth imports persons' routes held.
  - ~~`lib/server/auth-context.ts` and `lib/utils/with-role.ts`, the server guard~~: replaced by
    `features/auth/server/guard.ts` and deleted by #186 (2026-10-05), with `requireRole`,
    `requireServerRole`, `hasMinRole`, `hasMinServerRole` and the `/platform/metrics` probe.
  - ~~`lib/supabase/`~~: moved to `shared/supabase/` by #184 (2026-10-05). The grep for
    `@/lib/supabase` under `web/src` prints nothing.
  - ~~The auth types in `lib/types/api.ts`~~ (`UserProfile`, `UserClanMembership`,
    `UserClansResponse`, `ClanSwitchResponse`): deleted by #186 with their last reader.
  - `axios.ts` and `infrastructure/http/request-context.ts` are cross-cutting and leave with the last
    slice that imports them, not with auth.
- **`VerifyEmailScreen` (`src/features/auth/ui/VerifyEmailScreen.tsx`) is reachable from a real
  sign-in since #183.** Sign-in stays Supabase-direct (ADR-061 § 7), so the backend's
  `403 email_not_verified` is still never raised on the way. Supabase refuses a password sign-in
  for an unconfirmed account with the code `email_not_confirmed`, and `useAuthActions().signInWithEmail`
  routes that to `/{locale}/verify-email?email=…`. `features/auth/ui/LoginScreen.test.tsx` makes the
  fake Supabase client refuse with that code and reads the route; with the mapping removed it reads
  no route and Supabase's "Email not confirmed" on the form instead (run 2026-10-04).
