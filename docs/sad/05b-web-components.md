# 5.2 Web (frontend) — C4 Level 3 (Components)

`web/src/` · Next.js 16 App Router · React 19 · TypeScript strict · pnpm 10.
Mid-migration to layered DDD + Clean; legacy `src/lib/api` and `src/lib/hooks` are still
load-bearing.

## 5.2.1 Component diagram

```mermaid
graph TB
  browser([Browser]):::person

  mw[src/middleware.ts<br/>1 next-intl locale prefix<br/>2 strip prefix<br/>3 PUBLIC_ROUTES pass<br/>4 Supabase SSR session or redirect to login]:::comp

  subgraph pres[Presentation - src/app and src/components]
    rauth["[locale]/(auth)<br/>login, register, callback, pending-approval"]:::comp
    rdash["[locale]/(dashboard)<br/>protected app"]:::comp
    rback["[locale]/backoffice, platform, select-clan"]:::comp
    cmp[components/ui on Radix and Tailwind<br/>components/feature]:::comp
    xy[XYFlow tree canvas]:::comp
  end

  subgraph state[State]
    tq[TanStack Query<br/>lib/hooks/use*.ts<br/>query-invalidation.ts]:::comp
    zs[Zustand<br/>store/auth.store.ts - session, currentClanId<br/>store/ui.store.ts]:::comp
    rhf[react-hook-form and zod]:::comp
  end

  subgraph appl[application/feature - use-cases and ports]
    uc[admin · auth · documents · events<br/>persons · relationships · tree]:::comp
  end

  subgraph infra[infrastructure/feature - adapters]
    ad[HTTP adapters and DTO mappers]:::comp
    rc[infrastructure/http/request-context.ts<br/>single source of Accept-Language<br/>and X-Current-Clan-Id]:::comp
    qpol[infrastructure/http/query-policy.ts]:::comp
  end

  dom[domain/shared/types.ts<br/>framework-agnostic]:::core
  ax[lib/api/axios.ts<br/>interceptors add Bearer, Accept-Language<br/>and X-Current-Clan-Id · 401 signs out]:::comp
  sb[lib/supabase on @supabase/ssr]:::ext
  api[backend /api/v1]:::host

  browser --> mw
  mw --> rauth
  mw --> rdash
  mw --> rback
  rauth --> cmp
  rdash --> cmp
  rback --> cmp
  cmp --> xy
  cmp --> tq
  cmp --> zs
  cmp --> rhf
  tq --> uc
  uc --> ad
  uc --> dom
  ad --> rc
  ad --> qpol
  rc --> ax
  ax --> api
  mw --> sb
  zs --> sb
  ad -.->|must never be imported by| uc

  classDef person fill:#08427b,stroke:#052e56,color:#ffffff
  classDef host fill:#1168bd,stroke:#0b4884,color:#ffffff
  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef core fill:#e8a33d,stroke:#a9741f,color:#000000
  classDef ext fill:#999999,stroke:#6b6b6b,color:#ffffff
```

## 5.2.2 Layer rules

| Layer | May import | Must not import |
|---|---|---|
| `domain/` | nothing framework-y | React, Next, Axios, Supabase, Zustand, TanStack |
| `application/<feature>/` | domain, own ports | infrastructure implementations |
| `infrastructure/<feature>/` | application ports, axios, supabase | presentation |
| presentation (`app/`, `components/`, `lib/hooks/`, `store/`) | application use-cases | repositories directly |

Path alias `@/*` → `./src/*`.

## 5.2.3 Clan context resolution

```mermaid
graph LR
  s1[useAuthStore.currentClanId]:::comp
  s2[user.clan_id]:::comp
  s3[localStorage.current_clan_id]:::comp
  ssr[SSR render]:::comp
  rc["getRequestContext()"]:::comp
  hdr[X-Current-Clan-Id header]:::good

  s1 -->|first choice| rc
  s1 -->|else| s2
  s2 -->|else| s3
  s2 --> rc
  s3 --> rc
  ssr -.->|minimal context, locale vi| rc
  rc --> hdr

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef good fill:#4f9a68,stroke:#357049,color:#ffffff
```

**Rule:** never assemble the three contract headers ad-hoc — route through the shared
Axios instance or `getRequestContext()`.

## 5.2.4 i18n and routing

- `next-intl`, locales `vi | en | zh | fr`, default **`vi`**, `localePrefix: 'always'`
  → every route is `/vi/…`, `/en/…`. Config: `src/i18n/routing.ts`, strings in `messages/*.json`.
- If Supabase env vars are missing, the middleware **skips** the auth check — local-dev footgun.

## 5.2.5 Contract binding

Response handling must follow the frozen contract: `{data}` envelope, list `meta`
cursor pagination, `HistoricalDate` rendering (`date` when `precision === "exact"`,
else `display`), `profile` / `include` / `fields`.
**Gotcha:** keys from `include_by_id` must be merged into the sparse `fields` set or
compound includes are dropped.

⚠️ Legacy clients (`lib/api/auth.ts`, parts of `infrastructure/**`, member/tree types)
were scaffolded against **pre-envelope** shapes — see
[11-risks-and-technical-debt.md](11-risks-and-technical-debt.md).

## 5.2.6 Testing

Node built-in test runner only (no Jest/Vitest): `tests/behavior/*.test.ts`
(`pnpm test:behavior`) and `tests/contracts/*.test.mjs` (`pnpm test:contracts`).
Gate: `pnpm type-check && pnpm lint`.
