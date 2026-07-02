# Documentation Index

Project documentation for FamilyRoots — a Vietnamese genealogy platform with FastAPI backend, Next.js web, and Flutter mobile clients.

Per-service developer docs live next to the code in `backend/CLAUDE.md`, `web/CLAUDE.md`, and `mobile/CLAUDE.md`. This `docs/` tree holds **cross-cutting** design, contracts, operations, and decisions.

## Layout

```
docs/
├── README.md           # this index
├── architecture/       # cross-cutting design
├── contracts/          # public API + event contracts (one file per surface)
├── decisions/          # ADRs (architecture decision records, numbered)
├── ops/                # deployment, migrations, monitoring, incident response, secrets
├── guides/             # how-to guides: onboarding, IaC, Flutter build & lessons
├── plans/              # dated design + plan pairs for in-flight initiatives
└── prompts/            # paste-into-Gemini prompt templates (workflow tooling)
```

## Architecture

System-wide design that touches more than one service.

- [Overview](architecture/overview.md) — communication flows, failure assumptions, system map
- [Bounded Contexts](architecture/bounded-contexts.md) — domain context map, aggregates, cross-context relationships
- [Domain Rules](architecture/domain-rules.md) — genealogy invariants and error codes enforced in the domain layer
- [API Design](architecture/api-design.md) — REST conventions, pagination, sparse fields, includes
- [Data Model](architecture/data-model.md) — database schema reference
- [RBAC](architecture/rbac.md) — clan roles, permission model, hierarchy
- [Multi-Tenancy](architecture/multi-tenancy.md) — clan-scoped isolation (`X-Current-Clan-Id` + RLS)

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

## Plans

Dated in-flight initiatives. Each initiative is a `YYYY-MM-DD-<slug>-design.md` + `YYYY-MM-DD-<slug>-plan.md` pair.

## Prompts

Prompt templates for off-Claude tooling (e.g. pasting into Gemini). Not reference documentation — these are workflow scripts.

## Conventions

- One file per concern; prefer adding a focused doc over expanding an existing one.
- Cross-link aggressively: when a doc mentions another concept that has its own page, link to it.
- When you change a public API or an architectural rule, update the matching contract or ADR in the same PR.
- Section index README files (`contracts/`, `decisions/`, `ops/`) are the source of truth for what lives in that folder — keep them current.
