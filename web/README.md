# FamilyRoots Web

Frontend for the FamilyRoots platform, implemented with Next.js App Router and integrated with the FastAPI backend.

## Stack

- Next.js 16 + React 19
- TypeScript (strict mode)
- next-intl (vi/en/zh/fr)
- TanStack Query + Zustand
- Supabase auth (SSR/browser)
- Tailwind CSS + Radix UI

## Quick Start

1. Install dependencies:

```bash
pnpm install
```

2. Configure env:

```bash
cp .env.example .env.local
```

Required values:

- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

3. Run dev server:

```bash
pnpm dev
```

## Architecture Direction (DDD + Clean Architecture)

The web app is being incrementally migrated to layered frontend architecture:

- `src/domain`: framework-agnostic domain types and business rules
- `src/application`: use-cases and repository ports
- `src/infrastructure`: adapters (HTTP, Supabase, mappers)
- `src/components`, `src/app`, `src/lib/hooks`: presentation and route composition

### Dependency Rules

- Presentation can depend on application
- Application can depend on domain
- Infrastructure can depend on application and domain
- Domain must not import framework, transport, or UI code

## Backend Contract Requirements

All clan-scoped requests must send:

- `Authorization: Bearer <token>`
- `Accept-Language`
- `X-Current-Clan-Id`

Query semantics to preserve:

- Cursor pagination (`next_cursor`, `has_more`)
- `profile=summary|detail|full`
- `include` compound documents
- `fields` sparse fieldsets
- Batch include gotcha: include keys from `include_by_id` must be merged into sparse fields

## Scripts

- `pnpm dev`
- `pnpm build`
- `pnpm start`
- `pnpm type-check`
- `pnpm format`

## Superpowers Workflow

This repository uses the superpowers methodology (Claude Code plugin skills) for planning and implementation.

Recommended execution loop per feature slice:

1. Brainstorm and confirm design
2. Generate task plan with file-level actions
3. Execute in small batches via subagents
4. Run verification gates (type-check/tests)
5. Request code review before merge
