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
pnpm format                                    # prettier --write .
pnpm format:check
pnpm test:behavior                             # node --test on tests/behavior/*.test.ts (TS via --experimental-strip-types)
pnpm test:contracts                            # node --test on tests/contracts/*.test.mjs
node --test --experimental-strip-types tests/behavior/auth-and-invalidation.test.ts   # single behavior test
```

There is no Jest/Vitest — tests use the Node built-in test runner only.

Env vars in `.env.local` (see `.env.example`): `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

## Architecture

The app is mid-migration to **layered frontend architecture (DDD + Clean)**. Treat new code as the target shape; legacy code under `src/lib/api` and `src/lib/hooks` is being thinned but is still load-bearing.

### Layers and dependency rules

- `src/domain/` — framework-agnostic types, value objects, business rules. **Must not import** from React, Next, Axios, Supabase, Zustand, or TanStack Query.
- `src/application/<feature>/` — use-cases and repository **ports**. May import domain; must not import infrastructure implementations directly.
- `src/infrastructure/<feature>/` — HTTP adapters, DTO mappers, Supabase adapters; implements application ports. `src/infrastructure/http/request-context.ts` is the single source for `Accept-Language` + `X-Current-Clan-Id` resolution.
- Presentation: `src/app/` (App Router routes), `src/components/`, `src/lib/hooks/` (TanStack Query hooks), `src/store/` (Zustand stores). Calls application use-cases; keep business logic thin.

Path alias `@/*` → `./src/*` (tsconfig).

Feature slices currently present in both `application/` and `infrastructure/`: `admin`, `auth`, `documents`, `events`, `persons`, `relationships`, `tree` (plus `application/tree`). Use these as templates when adding a feature.

### Routing, locales, auth gating

- next-intl with locales `vi | en | zh | fr`, **default `vi`**, `localePrefix: 'always'` — every route is prefixed (`/vi/...`, `/en/...`). See `src/i18n/routing.ts` and `messages/*.json`.
- Route groups under `src/app/[locale]/`: `(auth)` (login/register/callback/pending-approval — public), `(dashboard)` (protected), plus `backoffice/`, `platform/`, `select-clan/`.
- `src/middleware.ts` runs the intl middleware first, strips the locale prefix, lets `PUBLIC_ROUTES` through, and for everything else creates a Supabase SSR client (`@supabase/ssr`) and redirects to `/<locale>/login` when there is no session. If Supabase env vars are missing the auth check is skipped — be aware in local dev.

### Backend contract — required headers and query semantics

All clan-scoped requests must send:

- `Authorization: Bearer <token>`
- `Accept-Language`
- `X-Current-Clan-Id`

The shared Axios client `src/lib/api/axios.ts` attaches all three via interceptors. On `401` it signs out and redirects to `/<locale>/login`. The clan id comes from `getRequestContext()` (`src/infrastructure/http/request-context.ts`), which reads in order: `useAuthStore.currentClanId` → `user.clan_id` → `localStorage.current_clan_id`. SSR returns a minimal context (`{ locale: 'vi' }`). When adding new HTTP adapters, route through this Axios instance or call `getRequestContext()` — do not assemble the headers ad-hoc.

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

- `tests/behavior/` — Node test runner with `--experimental-strip-types` for `.ts`. Focused on auth + query invalidation flows; use this for cross-layer behavior tests.
- `tests/contracts/` — `.mjs` contract tests that pin API client shapes. When you change a request/response shape on the backend, update the matching contract test.

## Migration notes

- `src/lib/api/*.ts` (legacy HTTP helpers) and `src/lib/hooks/use*.ts` predate the hexagonal split. New features should put transport in `src/infrastructure/<feature>/` and expose use-cases from `src/application/<feature>/`; the React Query hooks can stay in `src/lib/hooks/` but should call the application layer rather than `lib/api` directly.
- `src/domain/` is currently mostly `shared/`. As features migrate, domain types move out of `src/types/` and `src/lib/types/` into `src/domain/<feature>/`.
