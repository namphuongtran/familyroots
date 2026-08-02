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

### 1.1 Dependency upgrade sweep — backend + web

Bring every direct and transitive dependency to its latest stable release, and adopt
`httpx2` where it supersedes `httpx`.

- **Backend:** 71 outdated packages. Majors involved: `mypy` 1.19→2.x, `cryptography`
  46→50, `cachetools` 6→7, `rich` 14→15, `websockets` 15→17. Verified by the 1044-test
  suite plus the full gate.
- **Web:** ~35 outdated. Majors involved: `typescript` 5.9→7.0 (the native port),
  `tailwindcss` 3.4→4.3, `zod` 3.25→4.4, `eslint` 9→10, `@hookform/resolvers` 3→5,
  `tailwind-merge` 2→3, `lucide-react` 0.511→1.28, `@supabase/ssr` 0.6→0.12,
  `@types/node` 22→26.
- **`httpx2`:** `httpx` is frozen at 0.28.1; `httpx2` (pydantic org, 2.9.1) is the
  successor, and Starlette 1.x emits `StarletteDeprecationWarning` on every
  `TestClient` construction until it is installed. Retires the deferred item in §3.2.
- **Mobile:** blocked — no Flutter/Dart toolchain on this machine. `mobile/pubspec.yaml`
  still carries `flutter_bloc ^8`, `get_it ^7`, `go_router ^14`, `dio ^5`,
  `retrofit >=4 <5`, `hive ^2`, `intl ^0.20`. Run `flutter pub outdated` on a machine
  that has the SDK.

**Ordering constraint:** `tailwindcss` 4 and `zod` 4 land underneath sub-projects A
and B (§2.1, §2.2). Upgrading before those start is cheaper than migrating new code
afterwards — but it also means the web spine plan's pinned versions and its
hand-written zod boundary schemas must be re-checked against zod 4 before Task 1
begins.

---

## 2. Queued

### 2.1 Sub-project A — web architecture spine + observability

- **Spec:** `docs/superpowers/specs/2026-08-02-web-architecture-observability-design.md` (approved)
- **Plan:** `docs/superpowers/plans/2026-08-02-web-spine.md` — 12 tasks, **not started**
- **Status:** ready to execute, subject to the zod-4 recheck in §1.1.

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

**Known plan defects to warn implementers about:** the test bodies in Tasks 1 and 3 are
unverified. Implementers should fix a test that does not work rather than contorting the
implementation to satisfy a bad assertion. The plan's "Verification status (2026-08-02)"
section lists which claims were checked and which were not.

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

### 3.2 `StarletteDeprecationWarning` on every `TestClient`

Test output is no longer warning-free. Fixed by the `httpx2` adoption in §1.1; if that
slips, the fallback is a `filterwarnings` entry in `pyproject.toml`.

### 3.3 Stale remote branches

107 branches on `origin`. 100 local branches were deleted on 2026-08-02 — 94 that git
could prove merged, plus 6 squash-merged ones whose content was verified present in
`main`. Four of those 6 still exist on `origin` and are the recovery path if any of
those calls was wrong. Sweep the remote once enough time has passed, or enable
delete-branch-on-merge.

### 3.4 Pre-existing platform debt

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
| W3C trace context + Prometheus metrics (ADR-033) | `docs/superpowers/plans/2026-08-02-backend-trace-context-metrics.md` | `dc6f499`, CI green |
| Software Architecture Document (arc42 + C4) | `docs/sad/` | PR #121 |
| Backend production-readiness backlog | — | complete per owner sign-off |
| C1–C3 seam-review fixes | `docs/superpowers/plans/2026-07-04-seam-review-critical-fixes.md` | #22, #23, #24 |
