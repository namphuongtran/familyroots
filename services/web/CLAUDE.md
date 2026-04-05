# web

## Responsibility
Owns browser UX, admin workflows, and localized presentation for genealogy management.
It does not own canonical domain rules, persistence, or authorization policy decisions.

## Stack
- Next.js 16 + React 19 + TypeScript
- pnpm workspace package management
- TanStack Query + Zustand
- Supabase SSR auth client
- Tailwind CSS + Radix UI
- next-intl (vi/en/zh/fr)

## Domain Model
Domain and application layers mirror backend concepts for UI orchestration:
- Persons, relationships, documents, events, clans, auth session context
- Repositories in infrastructure adapt HTTP payloads into domain-friendly types

## API Surface
Consumes backend REST APIs:
- /api/v1/auth/*
- /api/v1/me/*
- /api/v1/clans/*
- /api/v1/persons/*
- /api/v1/relationships/*
- /api/v1/tree/*
- /api/v1/documents/*
- /api/v1/events/*

Uses request headers:
- Authorization bearer token
- X-Current-Clan-Id
- Accept-Language

## Event Contracts
Consumes:
- Backend REST contracts and auth session state

Publishes:
- User actions as HTTP mutations to backend
- No durable broker events owned by web app at present

## Data Ownership
No source-of-truth persistence ownership.
Owns client state snapshots, route state, and browser session behavior.

## Key Commands
- Dev: cd web && pnpm dev
- Build: cd web && pnpm build
- Lint: cd web && pnpm lint
- Type check: cd web && pnpm type-check
- Format: cd web && pnpm format

## Error Handling Pattern
- API errors are normalized through axios interceptors and surfaced to UI states.
- Query/mutation hooks drive retry and loading behavior.
- Route middleware enforces authenticated access in protected areas.

## Don't Do
- Do not embed backend secrets in client-side code.
- Do not bypass repository/application boundaries by calling axios directly from UI components.
- Do not hardcode locale text; use message catalogs.

## Known Issues / Landmines
- Test harness setup is incomplete compared to backend/mobile rigor. <!-- TODO: verify this -->
- Some backend endpoint shape assumptions changed over time and require contract sync checks. <!-- TODO: verify this -->
