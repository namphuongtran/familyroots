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
pnpm format                                    # prettier --write . — the 99-file pre-existing drift (seed S-028, 2026-08-22) is gone; safe to run, but keep it out of a behavioural PR's diff
pnpm format:check                              # prettier --check . — CI-gated since S-028
pnpm depcruise                                 # dependency-cruiser — enforces the layer rules below, CI-gated
pnpm gen:api [path/to/openapi.json]            # regenerate src/generated/api-types.ts from the backend's OpenAPI schema; no arg hits a running backend, a path arg reads a dumped schema (what CI uses)
pnpm test:unit                                 # vitest --project unit (node environment, *.test.ts under src/)
pnpm test:component                            # vitest --project component (jsdom, *.test.tsx, RTL + MSW)
pnpm test:e2e                                  # playwright test — boots `next dev` on :3100 itself
pnpm test:e2e:ui                                # playwright test --ui
pnpm test:behavior                             # legacy: node --test on tests/behavior/*.test.ts (TS via --experimental-strip-types)
pnpm test:contracts                            # legacy: node --test on tests/contracts/*.test.mjs
```

Full gate before calling anything done: `pnpm type-check && pnpm lint && pnpm format:check && pnpm depcruise && pnpm test:unit && pnpm test:component && pnpm test:e2e && pnpm build`. `pnpm test:e2e:auth` is **not** in that list and is not optional either — it needs Docker, the Supabase CLI stack and a seeded backend, so run it whenever you touch an authenticated route, and say plainly if you could not. See "The authenticated e2e harness" (seed S-070). Verify `pnpm lint` with the plain command — a clean run prints nothing, which is easy to misread as "didn't run."

**`pnpm format:check` has been in CI since seed S-028 (2026-08-22).** Before S-028, `web/CLAUDE.md`
and `.claude/rules/tailwind.md` § 9 both told contributors not to run `pnpm format`, because 112
files had accumulated pre-existing Prettier drift and a format run would bury the real diff in any
pull request. Re-counted at the start of S-028: `pnpm format:check` actually named **99** files,
not 112 — the figure had gone stale across three batches that added and deleted files in `web/`
since it was first measured, and nobody had re-run the count. S-028 ran `pnpm format --write .`
once, as its own single-purpose commit, landing all 99 files at once and touching nothing else.
`pnpm format` is safe to run now. The caution that follows is about diff hygiene, not about the
tool: running it inside a pull request that also changes behaviour still buries the real diff, so
keep a mechanical formatting pass in its own commit, the way S-028 did.

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

  `src/features/persons/{model,api}` landed 2026-08-22 by seed S-029, the first feature
  slice; `server/` and `hooks/` landed the same day by S-030; `ui/` landed the same day too,
  in two seeds — the list/detail screens (S-031) and the create/edit form (S-032) — see "The
  `persons` slice" and the two sections below it. New code that isn't a feature slice belongs
  in `src/domain/` or `src/shared/http/`, never in the legacy trees above.

Path alias `@/*` → `./src/*` (tsconfig).

### Dependency rules

**What the machine actually checks.** `.dependency-cruiser.cjs` holds nine rules, run by
`pnpm depcruise` and gated in CI. Every one of them _forbids_ something — dependency-cruiser
has no allow-list concept — so a rule name is the thing to grep for when a build fails:

| Rule                           | Forbids                                                                                                                                                                                                                                   | Severity |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| `domain-is-pure`               | `src/domain/**` importing any npm package except `typescript` / `@types/*` — which covers react, next, zod, tanstack, zustand and supabase                                                                                                | error    |
| `domain-imports-only-domain`   | `src/domain/**` importing anything under `src/` that is not `src/domain/`                                                                                                                                                                 | error    |
| `api-layer-has-no-react`       | `features/*/api/**` importing `react`, `react-dom` or `@tanstack/react-query`                                                                                                                                                             | error    |
| `ui-does-not-call-transport`   | `features/X/ui/**` importing `features/X/api/**`                                                                                                                                                                                          | error    |
| `cross-feature-only-via-index` | reaching into another feature's internals; `features/B` is importable only through `features/B/index.ts`                                                                                                                                  | error    |
| `app-does-not-call-transport`  | `src/app/**` importing `features/*/api/**`                                                                                                                                                                                                | error    |
| `nothing-imports-app`          | anything outside `src/app/` importing `src/app/**`                                                                                                                                                                                        | error    |
| `no-circular`                  | import cycles                                                                                                                                                                                                                             | error    |
| `no-orphans`                   | modules nothing imports — 3 known and accepted, measured 2026-08-22 by S-029: `shared/http/refresh.ts`, `lib/utils/pagination.ts`, `domain/capability/capability.ts` (the last is a known tool blind spot, see "Clan capabilities" below) | **warn** |

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

**`api-layer-has-no-react` was vacuous from the day it was written, on every package
manager, and S-029 (2026-08-22) is what found it.** `to.path` in dependency-cruiser
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

### The `persons` slice — the pattern S-029 set (`src/features/persons/{model,api}`)

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
  skipped. Verified during S-029 by changing `gender: z.enum(GENDERS)` to `z.number()`:
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
  the caller — `server/persons-repository.ts`, landed by S-030 below. This is
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
  things S-029 names: the `{"data": ...}` envelope, `Page<T>` via `unwrapPage`, and a
  `400 invalid_cursor` surfacing as `ApiError` with that `code`. All three have a proven
  negative control: breaking the mapper's `fullName` field, dropping the list query
  params, and swallowing the transport error each failed the named test for that reason,
  then were reverted.

### The `persons` repository, query keys, and hooks (S-030, `server/`, `hooks/`)

**`server/persons-repository.ts` is the fetch → parse → map step S-029 left open.** Every
function takes the `PersonsApiCallOptions` S-029's `api/` layer already defined
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
  `refreshAuth`, and asserting the underlying refresh operation ran once. **Building an
  actual browser `refreshAuth` — wiring `createSingleFlight` to a real Supabase
  `refreshSession()` call — is explicitly not done here.** No screen exists yet to need
  one (S-031/S-032), and no auth slice exists yet to own where a browser-wide singleton
  like that should live; inventing one now, untested against a real caller, would be the
  kind of decision a seed is supposed to isolate rather than smuggle into an unrelated one.
  A hook here only ever forwards whatever `refreshAuth` its caller passes in.
- **`batchGetPersons` gets its own small envelope reader rather than reusing
  `unwrapPage`.** `POST /persons/batch`'s `meta` is `{errors: BatchError[]}`, not the
  cursor triplet `unwrapPage` requires, so forcing it through `unwrapPage` would mean
  faking a `has_more`/`limit` that do not exist on the wire. `items` and `errors` are
  read and mapped separately and never merged — `docs/contracts/rest-persons-api.md` is
  explicit that an unresolved id is never mixed into `data`, and `PersonBatchResult`
  (`domain/person/person.ts`) keeps that shape in the return type too.
- **The `HistoricalDate` DTO stays duplicated — S-030 is not the second slice that needs
  it.** S-029 named `historical-date-dto.ts` as `persons`-local on purpose until a second
  _feature_ (marriages, events, tree nodes) needs the same wire shape. S-030 adds no new
  feature and no new wire shape; it is the same slice consuming what S-029 already parses.
  Nothing here changed about that file.
- **Write bodies still carry no zod validation, and this seed agrees with that call.**
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
themselves.** No screen exists yet (S-031/S-032) to decide how a context gets built and
kept reactive (almost certainly `useCurrentClanId()` plus the rest of the session), and
deciding that inside a hook nobody calls yet would be exactly the kind of premature
decision `.claude/rules/seeds.md` warns a seed against making for a later one. This keeps
every hook testable with a plain `RequestContext` object and MSW, which is what
`hooks/*.test.tsx` do.

- **Mutation invalidation is same-feature only, per this seed's own "Out of scope."**
  `useCreatePerson` invalidates `personsKeys.lists(clanId)`; `useUpdatePerson`,
  `useDeletePerson`, and `useRestorePerson` invalidate the one `personsKeys.detail(...)`
  plus every list. None of them touch `['tree']` the way the legacy
  `src/lib/hooks/query-invalidation.ts` does for the same mutations — cross-feature
  invalidation arrives with the second feature slice that needs to invalidate `persons`
  from outside it, per this seed's text.
- **The public surface changed shape.** Through S-029, `index.ts` re-exported the raw
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
this seed's real changes — the same three orphans S-029 already recorded, unaffected,
since `refresh.ts` is still imported only from `.test.ts` files, which the graph excludes.

### The persons create/edit form and its `409 stale_write` dialog (S-032, `ui/PersonForm.tsx`)

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
overflow at 1280px/200%. Screenshots were taken and reviewed, then discarded — see this seed's
closing note in `docs/SEEDS.md` for what was and was not verified this way.

**Scope this seed deliberately did not cover, named rather than left silent:**

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
_from_ an excluded file draws no edge, so `capability.ts` reads as orphaned no matter how real
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

  These four cover what only a browser can measure, and all four run against public routes.
  Authenticated routes are the section below.

- `pnpm test:e2e:auth` — the authenticated projects, off by default. See "The authenticated
  e2e harness" below. `pnpm test:e2e` does not run them and must never need Docker.

- `tests/behavior/` (legacy) — Node test runner with `--experimental-strip-types` for `.ts`.
  Focused on auth + query invalidation flows against the legacy trees; not part of the CI
  gate for new code.
- `tests/contracts/` (legacy) — `.mjs` contract tests that pin the legacy API client shapes.

CI (`.github/workflows/web-ci.yml`) runs type-check, lint, `depcruise`, unit, component,
build, e2e, and `api-types-fresh` (regenerates `src/generated/api-types.ts` from the
backend's OpenAPI schema and fails the build if it drifts — the anti-R3 gate). The
freshness job is triggered by changes under either `web/**` or `backend/app/**`, so a
backend-only PR that changes response shapes cannot skip it.

## The authenticated e2e harness (seed S-070, 2026-08-26)

**One command, and it is not part of `pnpm test:e2e`:**

```bash
# preconditions, from the repository root — see docs/ops/local-supabase.md and
# docs/ops/seed-test-users.md, which S-072 and S-073 own
docker compose up -d pgdb
scripts/supabase_local.sh up
make seed                                  # both halves of four test users

# a backend that trusts the LOCAL stack, and whose CORS admits the e2e origin.
# `docker compose up api` also works when the shell has no cloud Supabase values
# exported; the harness only needs some backend on E2E_AUTH_API_ORIGIN.
cd backend && DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/family_roots \
  SUPABASE_URL=http://supabase.localhost:54321 \
  SUPABASE_ANON_KEY=... SUPABASE_SERVICE_ROLE_KEY=...  \
  CORS_ORIGINS='["http://127.0.0.1:3102"]' APP_SECRET_KEY=e2e-local-secret \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8073

# then, in web/
export E2E_AUTH_STACK=1
export E2E_AUTH_SUPABASE_URL=http://supabase.localhost:54321   # NOT the 127.0.0.1 form
export E2E_AUTH_SUPABASE_ANON_KEY="$(scripts/supabase_local.sh env | ...)"
export E2E_AUTH_API_ORIGIN=http://127.0.0.1:8073
pnpm test:e2e:auth
```

**Nine tests, 2026-08-26**: two `auth-setup` logins and seven `auth-chromium` cases, one of
which is a deliberate `test.fail()` over an open T-04 defect (below).

### What holds the session, and why there is no stub

`e2e/auth/session.setup.ts` types a seeded user's real password into `/vi/login`, presses the
button, waits for the `sb-…-auth-token` cookie `@supabase/ssr` writes, and saves the context
with `storageState()` into `e2e/.auth/` (git-ignored — those files are live credentials).
`e2e/auth/backoffice.auth.spec.ts` then loads a state file per `test.describe`.

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
   `getServerAuthContext` produced
   `AssertionError: expected [ 'src/lib/server/auth-context.ts' ] to deeply equal []`,
   naming the file. Removed; the suite went back to 434 passing.
3. **The credential is worthless elsewhere.** `backoffice.auth.spec.ts`'s last case replays
   the captured admin state against the hermetic `:3100` server, which S-041 points at
   `https://e2e-fake-project.example.supabase.co`, and reads `307 → /vi/login`. Cookies are
   named for their project (`sb-<ref>-auth-token`) and the token is signed by the stack that
   issued it. **This does not prove middleware checks a signature — it does not**;
   `supabase.auth.getSession()` reads the cookie. Signature checking is the backend's JWKS
   flow (`backend/app/core/security.py`), which is S-072's guarantee, not this one's.

`E2E_AUTH_STACK=1` gates the projects _and_ the third `next dev` (`:3102`). Absent, neither
exists, so `pnpm test:e2e` keeps S-041's guarantee: no Docker, no network, same answer in a
fresh clone, in a worktree, and in CI. Present but under-configured, `authStackEnv()` throws
naming the missing variables — deliberately not a skip, because a suite that quietly covers
nothing when Docker is down is the "passed because it scanned nothing" failure
`.claude/rules/seeds.md` warns about.

### How to add the next authenticated route

1. **Pick a route whose gate is server-side.** Add a case to
   `e2e/auth/backoffice.auth.spec.ts`, or a new `e2e/auth/<name>.auth.spec.ts` — the
   `auth-chromium` project's `testMatch` picks up `e2e/auth/*.auth.spec.ts` with no config
   change. Reuse `SEEDED_USERS.admin.storageState` via `test.use({ storageState })`.
2. **Assert a role-dependent outcome, not the presence of markup.** One URL read with two
   sessions is the assertion that only a real session can produce. `page.request.get(path, {
maxRedirects: 0 })` reads a server-side gate as a status and a `Location` without
   mounting anything, which costs no renders and cannot be confused by a client effect.
3. **Give both Locations.** A viewer refused by `requireServerRole` gets
   `307 → /vi/dashboard`; a request with no session gets `307 → /vi/login`. If your two
   readings are the same string, you have S-001's non-control.
4. **Read colour schemes without reloading.** `page.emulateMedia({ colorScheme })`
   re-evaluates the media query in place, and ADR-045 made the media query the only
   mechanism. One page load per case matters: see the rate limit below.
5. **Budget the requests.** `/api/v1/auth/*` allows 20 requests per 60 seconds per IP
   (`backend/app/main.py:221-226`, hardcoded). One load of an authenticated screen spends
   about three `GET /auth/me`, because `useAuth()` hydrates once per consumer. Keep a case to
   one navigation.

### Three things S-070 found by looking, all of them still open

**1. `GET /me/clans` and `POST /me/clans/{id}/select` were read as unenveloped, and S-070
fixed both.** The web client read `{"clans": […]}` and `{clan_id: …}` while the backend has
always answered `{"data": …}` (`backend/app/api/v1/me.py:25,36`;
`Envelope_list_UserClanMembership__` at `src/generated/api-types.ts:2192-2196`;
`docs/contracts/frontend-integration-guide.md:77`). The first left `currentClanRole`
permanently `undefined`, so **every role-gated element on every server-rendered screen was
hidden and `requireServerRole` sent approved admins to `/pending-approval`**. The second wrote
the literal string `undefined` into the `current_clan_id` cookie. Both read sites are now
unwrapped in `HttpAuthProfileRepository`, which is the one place the port's shape is built —
see the doc comments there. **`register` and `onboard` in that same file have the identical
defect and are deliberately untouched**: they are the register/join path, fenced to S-084 on
2026-08-26. They need a seed.

**2. The `(dashboard)` group runs away, so `/vi/members` is not the covered route.** S-070's
first choice was `/vi/members`, the screen S-031, S-032 and S-036 each wanted. It cannot be
read: measured 2026-08-26, `/vi/dashboard` re-ran `useAuth`'s mount effect **2613 times in
seven seconds** and issued **18174 `GET /auth/me`** until the backend's limiter answered 429.
Two `useAuth()` consumers mount on every `(dashboard)` page (`(dashboard)/layout.tsx:12` and
`Header.tsx:18`), each hydrates independently, each hydration writes three fresh objects into
the zustand store, and `syncAuthContext`'s identity does not survive that. **The loop was
invisible before**, because the envelope defect above made `hydrateAuthContext` throw on its
first call and fall into its own `catch`; fixing the envelope is what let the loop start. It
is legacy auth code and its own seed — do not fix it inside a feature PR.

**3. "No horizontal page scroll" is not a usability reading, and this screen proves it.**
`e2e/text-scale.spec.ts`'s T-04 assertion passes on `/vi/backoffice/dashboard` at 320×640
with a 32px root, while every pixel of content is outside the viewport. Measured 2026-08-26:

```
aside     x=0    width=480      // `w-60` is 15rem = 480px at a 32px root
main      x=480  width=0        // `ml-60` adds another 480px; flex-1 collapses to zero
main h1   x=544  width=0
documentElement scrollWidth 320 === clientWidth 320, overflow-x: visible on html and body
```

Zero-width content cannot be scrolled to, so the page reports no overflow. The spec keeps the
scroll assertion (a reader will look for it) with a comment saying it proves almost nothing,
and pins the real defect with `test.fail()` so a future responsive fix turns the suite red
instead of leaving the case behind. `backoffice/layout.tsx:31-32` pairs a `fixed w-60` rail
with `ml-60` and has no small-screen branch. This is a fourth instance of the pattern in
`.claude/rules/seeds.md` § "A test pins an outcome, not a setting".

**Two smaller findings, reported and not fixed:** the login form's `<label>`s carry no
`htmlFor` and its inputs no `id`, so the email and password fields have no programmatic
label (`(auth)/login/page.tsx`); and `BackofficeSidebar.tsx:82` renders a hardcoded English
`Sign out` in a `vi`-default product, as `Sidebar.tsx:70` does with `aria-label="Thu gọn"`.

### The four workarounds this replaces

Four seeds each built a throwaway route, screenshotted it, and deleted it before committing,
because no test could hold a session. **Use this harness instead of rebuilding one.**

| Seed  | What it could not reach                        | What it did instead                            |
| ----- | ---------------------------------------------- | ---------------------------------------------- |
| S-031 | `/vi/members` with data                        | a throwaway route                              |
| S-032 | the conflict dialog (`StaleWriteDialog`)       | a throwaway preview route                      |
| S-036 | the calendar with data                         | a throwaway preview route                      |
| S-068 | ten converted files, none on a reachable route | its own verification was impossible as written |

S-039 / ADR-046 is the fifth case and the one now covered directly: it could not read the
backoffice rail in a browser and said so. `backoffice.auth.spec.ts` reads that rail's `muted`
ground and its `primary` mark in both schemes, which is ADR-046's own claim measured in an
engine rather than computed from the stylesheet.

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
