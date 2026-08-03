# 11. Risks and Technical Debt

## 11.1 Risk map

```mermaid
graph TB
  subgraph high[High]
    h1[R1 No staging · main reaches production]:::bad
    h2[R2 In-process event dispatcher is not durable]:::bad
    h3[R3 Web clients still bound to pre-envelope shapes]:::bad
  end

  subgraph medium[Medium]
    m1[R4 Mobile network and DI layer is scaffold · still on mocks]:::dec
    m2[R5 Pulumi resources are stubs · infra drift]:::dec
    m3[R6 Single API instance hosts the scheduler]:::dec
    m4[R7 Restore path untested · no RTO or RPO]:::dec
    m5[R8 Doc drift versus code]:::dec
  end

  subgraph low[Low]
    l1[R9 Scheduler hides PARTIAL FCM failure]:::comp
    l2[R10 Lunar range guard masks over-2199 as a 29-day month]:::comp
    l3[R11 Web test harness now spine-only · no feature slice coverage yet]:::comp
    l4[R12 Prompt-2 TODO scaffolds in scripts and infra]:::comp
    l5[R-lang Every page declares English to assistive technology]:::comp
  end

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef dec fill:#f5d76e,stroke:#b8a13c,color:#000000
  classDef bad fill:#c94f4f,stroke:#8f3636,color:#ffffff
```

## 11.2 Register

| # | Risk / debt | Impact | Current mitigation | Next move |
|---|---|---|---|---|
| R1 | **No staging gate** — merge to `main` deploys | A bad merge is a production incident | Full CI gate + migration-blocking pre-deploy + rollback path | Add a staging env / promotion flow |
| R2 | **In-process events** (ADR-004/005 deferred) | Handler failure rolls back the write; no cross-service integration | Deliberate: audit atomicity chosen over decoupling (ADR-014) | Build the Redis bus only when a second consumer exists |
| R3 | **Web pre-envelope clients** — `lib/api/auth.ts`, parts of `infrastructure/**`, member/tree types expect unwrapped bodies, `next_cursor`, scalar dates, `*_approx` | Runtime breakage as endpoints are adopted | The recurrence mechanism now exists: generated types (`src/generated/api-types.ts`) plus a CI `api-types-fresh` gate that fails the build if they drift from the backend's OpenAPI schema, triggered by either `web/**` or `backend/app/**` changes. The legacy clients themselves are still unmigrated | Feature slice PRs migrate each screen onto the spine (`shared/http`) and delete the matching legacy client |
| R4 | **Mobile still on mocks** — `api_client.dart`, `auth_interceptor.dart`, Firebase/Sentry/Hive init are TODO | Mobile has no real backend path yet | UI-first workflow is deliberate; DI flip is one line | Wire Dio interceptor with the 3 contract headers + 401 refresh |
| R5 | **Pulumi stubs** — `infra-ci.yml` `pulumi up` is a no-op | Declared infra ≠ real infra | Render/Vercel config is checked in and authoritative | Implement or explicitly retire the Pulumi path |
| R6 | **Single API instance hosts the scheduler** | Instance loss = missed job window that day | Advisory lock makes N instances safe; `notification_log` dedups | Scale out, or extract the job when the worker lands |
| R7 | **Backups unverified** | Unknown recovery time | Nightly `pg_dump` + rotation to the `backups` bucket | Run a restore drill; record RTO/RPO |
| R8 | **Doc drift** — the ADR index still calls ADR-008 "pilot only — inert at runtime"; `overview.md` and `multi-tenancy.md` describe an older RLS scope | Misleads the next reader on a security control | Code is the truth: RLS is live for `documents`, `events`, `branches`, `marriages`, `parent_child`, `persons` | Correct those three docs in one follow-up PR |
| R9 | **Scheduler partial-failure blindness** — `status = "sent" if sent > 0` with no `error_message` | A run with `sent>0 & failed>0` logs as clean success | Per-event try/rollback keeps the run alive | Record partial counts + error detail |
| R10 | **Lunar range masking** — `_days_in_lunar_month` catches `ValueError` broadly | Year > 2199 silently becomes a 29-day month | Engine range 1910–2199 is fail-loud elsewhere | Narrow the except clause |
| R11 | **Thin web tests** — was Node runner, behavior + contract suites only | Regressions land in the browser layer | Four harnesses now exist and are CI-gated: Vitest unit (55 tests), Vitest/RTL/MSW component (3 tests), Playwright e2e (real `next dev`, desktop + mobile viewport), `dependency-cruiser` layer rules. Coverage is the spine only — no feature slice has tests yet | Each feature slice PR adds unit/component/e2e coverage for its own screens |
| R12 | **`services/` legacy fence** | Cross-cutting code outside the hexagon | import-linter fences it; new aggregates go through `application/` | Keep the ratchet shrinking |
| R-lang | **Every page declares the wrong language to assistive technology.** `src/app/layout.tsx` hardcodes `<html lang="en">`, and `src/app/[locale]/layout.tsx` renders a `<div>`, so the selected locale never reaches the `lang` attribute. Screen readers apply English pronunciation rules to Vietnamese content across the whole product. Confirmed by request: `/vi/login` serves `<html lang="en">` | Every non-English page tells assistive technology it is English | Not fixed here — the fix is structural: `<html>`/`<body>` must move into a locale-aware layout while `src/app/page.tsx` and `src/app/api/*` still sit outside the `[locale]` segment. Tracked by a `test.fail()` in `web/e2e/smoke.spec.ts`: CI stays green while the bug exists and turns red the moment it is fixed, forcing the assertion to be promoted to a normal test rather than quietly lost | **Owner: PR 1 (auth slice)**, which already rewrites the locale, cookie and middleware machinery |

## 11.3 Debt principles in force

- **Ratchet, never loosen:** import-linter `ignore_imports` lists may shrink, never grow.
- **`_(planned)_` must stay honest** — if it isn't built, it says so.
- **Code wins over docs** — when they disagree, fix the doc in the same PR.
