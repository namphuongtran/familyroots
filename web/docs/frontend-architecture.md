# Frontend Architecture (Incremental DDD + Clean Architecture)

This document defines the target architecture for the FamilyRoots web application and the migration strategy from the current feature-slice implementation.

## Goals

- Keep delivery velocity while reducing coupling to transport and framework details.
- Make business behavior testable with domain + application tests.
- Preserve existing backend API contracts and avoid regressions.

## Layer Model

## Domain

Location: `src/domain`

Responsibilities:

- Domain types and value objects
- Business invariants and pure rules
- No framework imports

Rules:

- Must not import from React, Next.js, Axios, Supabase, Zustand, or TanStack Query.

## Application

Location: `src/application`

Responsibilities:

- Use-cases and orchestration
- Repository/service ports
- Input/output contracts for UI-facing workflows

Rules:

- May import domain
- Must not import infrastructure implementations directly

## Infrastructure

Location: `src/infrastructure`

Responsibilities:

- HTTP adapters
- Supabase adapters
- DTO mappers
- Request context and transport policies

Rules:

- Implements application ports
- Can import application/domain/lib types

## Presentation

Location: `src/app`, `src/components`, `src/lib/hooks`, `src/store`

Responsibilities:

- Routes, components, and interaction state
- Calls application use-cases
- Keeps business logic thin

Rules:

- Can depend on application
- Should not include transport-specific parsing rules

## Current Implemented Foundation

1. Shared request context utility
   - `src/infrastructure/http/request-context.ts`
   - Standardizes locale and clan context for all HTTP calls.

2. Query policy utility
   - `src/infrastructure/http/query-policy.ts`
   - Enforces include/fields normalization and batch include-by-id handling.

3. Persons application port + use-cases
   - `src/application/persons/ports/person-query-repository.ts`
   - `src/application/persons/use-cases/person-queries.ts`

4. Persons infrastructure adapter
   - `src/infrastructure/persons/person-query-repository.ts`

5. Hook migration to application layer
   - `src/lib/hooks/useMembers.ts` now uses application use-cases for reads.

6. Auth + clan context application/infrastructure layering
   - `src/application/auth/ports/auth-repository.ts`
   - `src/application/auth/use-cases/auth-context.ts`
   - `src/infrastructure/auth/http-auth-profile-repository.ts`
   - `src/infrastructure/auth/supabase-auth-session-port.ts`
   - `src/lib/hooks/useAuth.ts` now hydrates auth context via use-cases.

7. Tree read flow layering
   - `src/application/tree/ports/tree-query-repository.ts`
   - `src/application/tree/use-cases/tree-queries.ts`
   - `src/infrastructure/tree/tree-query-repository.ts`
   - `src/lib/hooks/useFamilyTree.ts` now uses tree query use-cases.

8. Events read flow layering
   - `src/application/events/ports/event-query-repository.ts`
   - `src/application/events/use-cases/event-queries.ts`
   - `src/infrastructure/events/event-query-repository.ts`
   - `src/lib/hooks/useEvents.ts` now uses event query use-cases.

9. Documents read flow layering
   - `src/application/documents/ports/document-query-repository.ts`
   - `src/application/documents/use-cases/document-queries.ts`
   - `src/infrastructure/documents/document-query-repository.ts`
   - `src/lib/hooks/useDocuments.ts` now uses document query use-cases for reads.

## API Contract Invariants

1. Headers

- Always send Authorization bearer token if present.
- Always send `Accept-Language`.
- Always send `X-Current-Clan-Id` when available.

2. Query semantics

- Cursor pagination must use opaque `next_cursor`.
- `profile` accepted values: `summary`, `detail`, `full`.
- When both `include` and `fields` are present, include keys must be added to sparse fields.
- In batch calls, include keys from `include_by_id` must be merged with global include before sparse filtering.

## Migration Sequence (Next)

1. Migrate auth/clan switching and RBAC checks into application services.
2. Migrate tree and relationship read flows to ports/use-cases/adapters.
3. Migrate events and documents flows.
4. Migrate admin/platform admin flows.
5. Remove legacy direct transport hooks once parity is verified.

## Verification Gates

- Type-check must pass.
- Integration checks for clan header behavior and role-guarded routes.
- Contract tests for include/fields/profile and cursor behavior.
