---
paths:
  - "web/**/*.{ts,tsx,mts,mjs,css}"
---

# Next.js rules (the `web/` app)

Scope: the `web/` service only. Next.js 16 App Router, React 19, TypeScript 6 with
`strict: true`, pnpm 10.

Source: adapted from
[github/awesome-copilot `instructions/nextjs.instructions.md`](https://github.com/github/awesome-copilot/blob/main/instructions/nextjs.instructions.md)
(dated January 2026, aligned to Next.js 16.1.1). That guide describes a generic Next.js app.
This repo differs in several places, and the differences are listed below. When this file and
the upstream guide disagree, this file wins. `web/CLAUDE.md` owns the full architecture
description; do not duplicate it here.

Facts about the repo in this file were checked on 2026-08-13. Re-check before you trust one.

## 1. Where code goes

Do not apply the generic layout (`lib/`, `components/`, `contexts/`, `hooks/`, `types/` at the
top level). This repo has its own layout, and `pnpm depcruise` enforces part of it in CI.

- Read the layout and the nine dependency-cruiser rules in `web/CLAUDE.md` before you add a
  file.
- New code belongs in `src/domain/`, `src/shared/`, or `src/features/<slice>/`.
- `src/lib/api/`, `src/lib/hooks/`, `src/application/`, and `src/infrastructure/` are frozen
  legacy trees. Do not add to them.
- Route groups: `(auth)` and `(dashboard)` under `src/app/[locale]/`. Every route is locale
  prefixed, because `localePrefix` is `'always'`.
- `src/app/**` holds routing only: `layout`, `page`, `loading`, `error`, `not-found`.

## 2. Server and Client components

- Server Components are the default. Use them for data fetching and non-interactive UI.
- Add `'use client'` only for state, effects, browser APIs, or event handlers.
- Never call `next/dynamic` with `{ ssr: false }` inside a Server Component. It is not
  supported and it breaks the build.
- To use client-only UI inside a Server Component, move that UI into one Client Component and
  import it directly. Compose several client-only parts into a single Client Component.
- Keep client bundles small. Push logic down into Server Components and `src/domain/`.

## 3. Async request APIs

In Next.js 16 the request-bound APIs are async in the App Router.

- Always `await cookies()`, `await headers()`, and `await draftMode()`. The repo already does
  this in `web/src/shared/http/context.server.ts` and
  `web/src/app/api/auth/callback/route.ts`.
- Treat `params` and `searchParams` in Server Components as Promises. `await` them.
- Reading request data makes a route dynamic. Read it on purpose, and put dynamic parts behind
  a `Suspense` boundary when the rest of the page can be static.

## 4. Route handlers

The backend is FastAPI. Business logic lives there, not in `web/`.

- Today there is exactly one route handler: `web/src/app/api/auth/callback/route.ts`.
- Do not add a route handler to proxy or re-wrap a backend endpoint. Call the backend through
  `apiFetch` instead.
- Add a route handler only when the browser needs a same-origin server endpoint, for example
  an auth callback that must set cookies.
- Never `fetch('/api/...')` from a Server Component. Import the shared module and call it
  directly.
- If you do add one: validate input with `zod`, export async functions named after the HTTP
  verb, and return the correct status code.

## 5. Backend calls, envelope, and errors

- `apiFetch` (`web/src/shared/http/api-client.ts`) is the only way to reach the backend. It
  builds `Authorization`, `Accept-Language`, `X-Current-Clan-Id`, and `traceparent`.
- Pass `RequestContext` in. Never read it from a global.
- `unwrapData` and `unwrapPage` (`web/src/shared/http/envelope.ts`) are the only readers of
  the `{"data": ...}` envelope. No component sees the wrapped shape.
- Branch on the error `code`, never on `message`. The backend sends `message` already
  localized.
- Render dates through `HistoricalDate` (`web/src/domain/date/historical-date.ts`). Do not
  re-implement the render rule.

## 6. Caching and revalidation

Cache Components are **not** enabled in this repo. `web/next.config.ts` has no
`cacheComponents` key, and no file under `web/src/` uses `use cache`, `cacheTag`, `cacheLife`,
or `revalidateTag`.

- Do not write `use cache` or `cacheTag(...)` unless the same pull request also sets
  `cacheComponents: true` in `web/next.config.ts`. The directive is inert without the flag.
- Enabling Cache Components is an architecture change. Write an ADR under `docs/decisions/`
  first.
- Do not add `unstable_cache` to new code. It is legacy.
- When Cache Components are on, prefer `revalidateTag(tag, 'max')`. Use `updateTag(...)`
  inside a Server Action when a write must be visible on the next read.

## 7. Naming

Match what the code already does.

- Folders: `kebab-case`, for example `src/components/family-tree/`.
- React component files: `PascalCase`, matching the component name, for example
  `MemberCard.tsx`. 25 of the 27 `.tsx` files under `src/components/` follow this.
- Domain, shared, and transport modules: `kebab-case`, for example `api-client.ts`,
  `historical-date.ts`.
- Hooks: `camelCase` with a `use` prefix, for example `useAuth.ts`.
- Zustand stores: `<name>.store.ts`, for example `auth.store.ts`.
- Tests sit next to the file they test: `historical-date.test.ts`, `msw.test.tsx`.
- Variables and functions `camelCase`, types and interfaces `PascalCase`, constants
  `UPPER_SNAKE_CASE`.

## 8. Config, tooling, and environment

- Turbopack is the default dev bundler in Next.js 16. If you need bundler config, use the
  top-level `turbopack` field. `experimental.turbo` was removed.
- `web/next.config.ts` is wrapped by `withSentryConfig(withNextIntl(...))`. Keep Sentry
  outermost when you change it.
- Lint through the ESLint CLI: `pnpm lint` runs `eslint .`. Do not switch to `next lint`.
- `serverRuntimeConfig` and `publicRuntimeConfig` are removed in Next.js 16. Use environment
  variables.
- `NEXT_PUBLIC_*` values are inlined at build time. Changing one after a build does not affect
  the deployed build.
- Secrets go in `.env.local`, which is never committed.
- `typedRoutes` is not enabled today. Turning it on is a separate, deliberate change.

## 9. Testing

The upstream guide names Jest. This repo does not use Jest.

- `pnpm test:unit` — Vitest, node environment, `*.test.ts` under `src/`.
- `pnpm test:component` — Vitest, jsdom, `*.test.tsx`, React Testing Library plus MSW.
- `pnpm test:e2e` — Playwright. It boots `next dev` on port 3100 itself.
- MSW handlers build real envelopes. A test must not invent a response shape.

## 10. Before you claim the work is done

Run the full gate:

```bash
cd web && pnpm type-check && pnpm lint && pnpm depcruise \
  && pnpm test:unit && pnpm test:component && pnpm test:e2e && pnpm build
```

A clean `pnpm lint` prints nothing. That looks like a command that did not run, so read the
exit code.

Do not run `pnpm format`. `web/CLAUDE.md` records that 112 files already have Prettier drift,
so a format run buries the real diff. Use `pnpm format:check` if you need to look.

## 11. Two habits to keep

- Do not create example or demo files, such as `ModalExample.tsx`, in the main tree. Add one
  only when the user asks for a live example or a documentation component.
- Check current documentation before you answer a framework question. Use the context7 MCP
  tools: `resolve-library-id`, then `query-docs`. Training data lags the framework.
