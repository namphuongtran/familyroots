# Documentation Index

Project documentation for FamilyRoots — a Vietnamese genealogy platform with FastAPI backend, Next.js web, and Flutter mobile clients.

Per-service developer docs live next to the code in `backend/CLAUDE.md`, `web/CLAUDE.md`, and `mobile/CLAUDE.md`. This `docs/` tree holds **cross-cutting** design, contracts, operations, and decisions.

## Layout

```
docs/
├── README.md           # this index
├── roadmap.md          # the milestone order, and the reason for each boundary
├── SEEDS.md            # the only tracker: seeds, items owed, and claims not verified
├── sad/                # Software Architecture Document (arc42 + C4) — start here for the big picture
├── architecture/       # cross-cutting design
├── contracts/          # public API + event contracts (one file per surface)
├── decisions/          # ADRs (architecture decision records, numbered)
├── ops/                # deployment, migrations, monitoring, incident response, secrets
└── guides/             # how-to guides: onboarding, IaC, Flutter build & lessons
```

## Read this first (required pre-task reading)

Before starting a task, read the docs that own the surface you're touching:

| Task touches… | Read first |
|---|---|
| Any public API request/response shape | [contracts/README.md](contracts/README.md) (envelope + HistoricalDate) + the matching `contracts/rest-*.md` |
| Database schema / migrations | [architecture/data-model.md](architecture/data-model.md) + [ops/migrations.md](ops/migrations.md) |
| Tree / đời / kinship / đa thê | [architecture/tree-read-model.md](architecture/tree-read-model.md) + [architecture/domain-rules.md](architecture/domain-rules.md) |
| Auth / login / roles / clan context | [architecture/auth-flow.md](architecture/auth-flow.md) + [architecture/rbac.md](architecture/rbac.md) + [architecture/multi-tenancy.md](architecture/multi-tenancy.md) |
| Genealogy business rules | [architecture/domain-rules.md](architecture/domain-rules.md) |
| An architectural choice (or breaking change) | [decisions/README.md](decisions/README.md) — and add an ADR in the same PR |
| Deploy / infra / incidents | [ops/README.md](ops/README.md) |
| Picking up work: which ticket to take next | [SEEDS.md](SEEDS.md) — start at any seed whose `Blocked by` is `none` |
| Planning: what order the milestones run in, and why | [roadmap.md](roadmap.md) |
| How a ticket is written here | [../.claude/rules/seeds.md](../.claude/rules/seeds.md) |

## Software Architecture Document (SAD)

The whole-system view, **arc42** structure with **C4** diagrams (Context → Container →
Component → Code), covering backend, web, mobile, and database. Start at
[sad/README.md](sad/README.md) — it is a synthesis; the per-surface docs below stay
authoritative.

## Architecture

System-wide design that touches more than one service.

- [Overview](architecture/overview.md) — communication flows, failure assumptions, system map
- [Backend Developer Guide](architecture/backend-developer-guide.md) — detail design: how to build an aggregate (Person is the canonical reference)
- [Bounded Contexts](architecture/bounded-contexts.md) — domain context map, aggregates, cross-context relationships
- [Domain Rules](architecture/domain-rules.md) — genealogy invariants and error codes enforced in the domain layer
- [API Design](architecture/api-design.md) — REST conventions, endpoint inventory, pagination, sparse fields, includes
- [Data Model](architecture/data-model.md) — database schema reference
- [RBAC](architecture/rbac.md) — clan roles, permission model, hierarchy
- [Multi-Tenancy](architecture/multi-tenancy.md) — clan-scoped isolation (`X-Current-Clan-Id`; row-level security live on 6 of 14 clan-owned tables, measured 2026-08-13 — the other 8 are seeds S-008 to S-014)
- [Auth Flow](architecture/auth-flow.md) — JWT/JWKS pipeline, email verification, authorization gates
- [Tree Read-Model](architecture/tree-read-model.md) — computed đời, đa thê mother attribution, SQL tree functions
- [Backend i18n](architecture/i18n.md) — locale resolution, `t()` fallback chain, key namespaces, coverage guard
- [Notifications & Scheduler](architecture/notifications-scheduler.md) — anniversary cron, advisory lock, FCM delivery (solar + lunar giỗ, see ADR-018)
- [File Storage](architecture/storage.md) — bucket layout, presigned URLs, upload limits, soft-delete + retention purge lifecycle (ADR-019)

## Contracts

Canonical public API + event contracts. Start at [contracts/README.md](contracts/README.md).

## Decisions

Numbered ADRs. Start at [decisions/README.md](decisions/README.md).

## Ops

Runbooks for production operations. Start at [ops/README.md](ops/README.md).

## Guides

- [Developer Onboarding](guides/onboarding.md)
- [Infrastructure as Code Guide](guides/iac-guide.md)
- [Flutter Build & Publish](guides/flutter-build-publish.md)
- [Flutter Lessons](guides/flutter-lessons.md)

## Conventions

- One file per concern; prefer adding a focused doc over expanding an existing one.
- Cross-link aggressively: when a doc mentions another concept that has its own page, link to it.
- When you change a public API or an architectural rule, update the matching contract or ADR in the same PR.
- Section index README files (`contracts/`, `decisions/`, `ops/`) are the source of truth for what lives in that folder — keep them current.
