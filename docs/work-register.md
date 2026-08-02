# Work Register

**What this is:** the running list of what is in flight, what is queued, and what
we have knowingly left undone. Specs and plans hold the *how*; this file holds the
*state* — which of them are live, which are finished, and which decisions were made
outside any document.

**Keep it current.** Update this file in the same PR that changes the state of an
item. When an item is finished, move it to *Landed* with its merge commit, and delete
it once the git history and the ADRs tell the story on their own.

Last updated: 2026-08-02.

---

## 1. In flight

### 1.1 Dependency upgrade sweep — mobile remainder

Backend and web are done (see §4). What is left:

- **Mobile:** blocked — no Flutter/Dart toolchain on this machine.
  `mobile/pubspec.yaml` still carries `flutter_bloc ^8`, `get_it ^7`, `go_router ^14`,
  `dio ^5`, `retrofit >=4 <5`, `hive ^2`, `intl ^0.20`. Run `flutter pub outdated` on
  a machine that has the SDK.

Three upgrades were attempted and deliberately not taken, each blocked upstream
rather than by our code:

| Package | Wanted | Landed | Why |
|---|---|---|---|
| `typescript` | 7.0.2 | 6.0.3 | typescript-eslint hard-errors on TS 7 (`typescript-eslint#10940`, targets ≥7.1), and eslint-config-next loads it, so the whole lint step dies. TS 7 itself type-checks and builds fine. |
| `eslint` | 10.8.0 | 9.39.5 | `eslint-plugin-react`'s latest release (7.37.5) declares `eslint: ^3 \|\| … \|\| ^9.7` and throws inside `usedPropTypes` on v10. `eslint-config-next` depends on it. |
| `firebase-admin` `Message.fid` | — | kept `token` | `fid` is a Firebase Installation ID, `token` a device registration token — distinct, mutually exclusive wire fields. Switching needs the Flutter client to send installation IDs first. The deprecation warning is filtered by exact message. |

Re-check all three when the upstream packages move.

**Consequence for sub-project A (§2.1):** resolved. The spine plan was re-verified on
2026-08-02 against the upgraded tree; its Global Constraints now state the zod-4
`z.input`/`z.output` rule for the slice PRs that will write boundary schemas.

---

## 2. Queued

### 2.1 Sub-project A — web architecture spine + observability

- **Spec:** `docs/superpowers/specs/2026-08-02-web-architecture-observability-design.md` (approved)
- **Plan:** `docs/superpowers/plans/2026-08-02-web-spine.md` — **13 tasks** (0–12), Task 0 done
- **Status:** executing. The zod-4 recheck flagged in §1.1 is done.

**Task 0 landed** (`8f7abb4`): Node floor raised to 22 — `web/.nvmrc`, `engines.node
>=22.12.0`, `pnpm.onlyBuiltDependencies: ["@sentry/cli"]`, and `node-version: 22` in both
`web-ci.yml` jobs. Verified on Node 24.15.0: install, `type-check`, `lint` and `build` all
green, lockfile unchanged (so `--frozen-lockfile` still holds). **Open owner action:**
confirm the Vercel project runtime is Node 22.x or 24.x — the repo has no `vercel.json`,
so the runtime comes from the dashboard setting plus this new `engines.node` range.

**Second verification pass, 2026-08-02.** Every implementation module and test body in
the plan was executed in a throwaway project carrying the exact installed toolchain:
**8 files, 55 tests, all passing, `tsc --noEmit` clean.** The OpenAPI generator, the
Sentry + Next 16 build, the dependency-cruiser rules, and the Playwright harness were
each run for real. Twelve defects were found and fixed in the plan — including three
that would have failed on the first run: CI pins Node 20 while `jsdom@30`,
`jest-dom@7` and `dependency-cruiser@18` all require ≥22 (now **Task 0**); six
`vi.fn` mocks in Task 7 that do not compile; and an E2E assertion of `lang="vi"`
against an app that serves `lang="en"`. The plan's "Verification status — second pass"
and "Defects found and fixed" sections carry the evidence.

Decisions taken during design that live nowhere else:

| Question | Decision |
|---|---|
| Sub-project order | A → B → D, with C (observability) folded into A |
| Restructure depth | Real domain layer + typed repositories; no port-interface or use-case class per CRUD operation |
| UI scope inside A | Move components into feature slices, keep the current look |
| Trace propagation | W3C `traceparent`, exported through Sentry |
| DTO drift protection | Generate types from OpenAPI, hand-write zod schemas at the boundary |
| Test harness | Vitest + React Testing Library + MSW + Playwright |
| Scope | The whole restructure, split into sequential per-slice PRs |
| Rendering | Server-fetch the first page, client-side for interaction |

**What is still unverified:** `pnpm build` of the real `web/` tree with Sentry added
(the composition was proved on a minimal Next 16 app); Playwright inside GitHub Actions;
and the component project under CI's Node rather than local Node 24. Everything else was
executed. Implementers should still fix a test that does not work rather than contorting
the implementation to satisfy a bad assertion.

### 2.2 Sub-project B — design system and UX for all ages

Not yet specced. Follows A. Interacts with the `tailwindcss` 4 migration in §1.1.

### 2.3 Sub-project D — mobile

Not yet specced. Follows B.

---

## 3. Open gaps — knowingly unfixed

### 3.1 `METRICS_TOKEN` hardening

`/internal/metrics` compares a bearer token with `secrets.compare_digest` and returns
404 on every failure (ADR-021 non-enumeration). Missing: an entropy floor on the
configured token, and rate limiting — failed attempts are silent 404s that sit outside
the rate limiter, so the endpoint can be brute-forced without trace. Recorded in
`docs/ops/monitoring.md`. **Decide before anything scrapes the endpoint.**

### 3.2 R-lang — every page declares the wrong language

`src/app/layout.tsx` hardcodes `<html lang="en">`, and `src/app/[locale]/layout.tsx`
renders a `<div>`, so the selected locale never reaches the `lang` attribute. Screen
readers apply English pronunciation rules to Vietnamese content across the whole
product. Confirmed by request: `/vi/login` serves `<html lang="en">`.

The fix is structural — `<html>`/`<body>` must move into a locale-aware layout while
`src/app/page.tsx` and `src/app/api/*` still sit outside the `[locale]` segment.
**Owner: sub-project A, PR 1 (auth)**, which already rewrites the locale, cookie and
middleware machinery. A `test.fail()` in `web/e2e/smoke.spec.ts` (added by spine
Task 11) keeps CI green while the bug exists and turns red the moment it is fixed.

### 3.3 `pnpm format:check` fails on 112 web files

Pre-existing prettier drift in files no recent branch has touched
(`src/middleware.ts`, `src/store/auth.store.ts`, `tsconfig.json`, …). It is not part
of the documented web gate (`pnpm type-check && pnpm lint`), so CI stays green.
Running `pnpm format` would fix it in one sweep at the cost of a 112-file diff —
worth folding into sub-project A rather than doing standalone.

### 3.4 Stale remote branches

107 branches on `origin`. 100 local branches were deleted on 2026-08-02 — 94 that git
could prove merged, plus 6 squash-merged ones whose content was verified present in
`main`. Four of those 6 still exist on `origin` and are the recovery path if any of
those calls was wrong. Sweep the remote once enough time has passed, or enable
delete-branch-on-merge.

### 3.5 Pre-existing platform debt

Carried from `CLAUDE.md` — none of these are scheduled:

- Pulumi resources are stubs; deployment drift is possible.
- The in-process event dispatcher has no durable delivery guarantee. Do not treat
  in-process events as integration events without explicit mitigation.
- Prompt-2 TODO scaffolds remain across mobile, infra, and helper scripts.
- The web test harness is thinner than backend/mobile — sub-project A (§2.1) is the fix.

---

## 4. Landed recently

| Work | Where | Merge |
|---|---|---|
| Backend dependency sweep + httpx2 (71 packages, 5 majors) | `backend/pyproject.toml` | `d2d2de1` |
| Web dependency sweep: Tailwind 4, zod 4, TS 6 | `web/package.json` | `a457e29`, `5f4cb7f`, `5dc340a`, `e3ce8d8` |
| W3C trace context + Prometheus metrics (ADR-033) | `docs/superpowers/plans/2026-08-02-backend-trace-context-metrics.md` | `dc6f499`, CI green |
| Software Architecture Document (arc42 + C4) | `docs/sad/` | PR #121 |
| Backend production-readiness backlog | — | complete per owner sign-off |
| C1–C3 seam-review fixes | `docs/superpowers/plans/2026-07-04-seam-review-critical-fixes.md` | #22, #23, #24 |
