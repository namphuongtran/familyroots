# Software Architecture Document (SAD)

FamilyRoots — Vietnamese genealogy platform. Structure: **arc42** (12 sections).
Views: **C4** (Context → Container → Component → Code). Diagrams: Mermaid.

**Status:** as-built on `main` (2026-08-02). Code is the source of truth.
_(planned)_ marks target state that is **not** implemented.

## Reading order — overview to detail

| # | arc42 section | C4 level | Doc |
|---|---|---|---|
| 1 | Introduction & Goals | — | [01-introduction-and-goals.md](01-introduction-and-goals.md) |
| 2 | Constraints | — | [02-architecture-constraints.md](02-architecture-constraints.md) |
| 3 | Context & Scope | **L1 Context** | [03-context-and-scope.md](03-context-and-scope.md) |
| 4 | Solution Strategy | — | [04-solution-strategy.md](04-solution-strategy.md) |
| 5 | Building Blocks | **L2 Container** | [05-building-block-view.md](05-building-block-view.md) |
| 5.1 | ↳ backend | **L3 + L4** | [05a-backend-components.md](05a-backend-components.md) |
| 5.2 | ↳ web (frontend) | **L3** | [05b-web-components.md](05b-web-components.md) |
| 5.3 | ↳ mobile | **L3** | [05c-mobile-components.md](05c-mobile-components.md) |
| 5.4 | ↳ database | **L3** | [05d-database-components.md](05d-database-components.md) |
| 6 | Runtime View | — | [06-runtime-view.md](06-runtime-view.md) |
| 7 | Deployment View | — | [07-deployment-view.md](07-deployment-view.md) |
| 8 | Cross-cutting Concepts | — | [08-crosscutting-concepts.md](08-crosscutting-concepts.md) |
| 9 | Decisions | — | [09-architecture-decisions.md](09-architecture-decisions.md) |
| 10 | Quality Requirements | — | [10-quality-requirements.md](10-quality-requirements.md) |
| 11 | Risks & Technical Debt | — | [11-risks-and-technical-debt.md](11-risks-and-technical-debt.md) |
| 12 | Glossary | — | [12-glossary.md](12-glossary.md) |

## Diagram conventions

One palette across every view, so a colour means the same thing at every C4 level.

```mermaid
graph LR
  person([Person<br/>human actor]):::person
  host[Container<br/>deployable unit]:::host
  comp[Component<br/>module inside a container]:::comp
  core[Domain core<br/>framework-agnostic]:::core
  store[(Data store)]:::store
  ext[External system]:::ext
  planned[Planned / deferred<br/>not built]:::v2
  dec{Decision}:::dec
  good[Success outcome]:::good
  bad[Failure outcome]:::bad

  person --> host
  host --> comp
  comp --> core
  comp --> store
  host --> ext
  host -.-> planned
  host --> dec
  dec -->|yes| good
  dec -->|no| bad

  classDef person fill:#08427b,stroke:#052e56,color:#ffffff
  classDef host fill:#1168bd,stroke:#0b4884,color:#ffffff
  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef core fill:#e8a33d,stroke:#a9741f,color:#000000
  classDef store fill:#438dd5,stroke:#2e6295,color:#ffffff
  classDef ext fill:#999999,stroke:#6b6b6b,color:#ffffff
  classDef v2 fill:#7b4fa0,stroke:#54356f,color:#ffffff,stroke-dasharray:5 4
  classDef dec fill:#f5d76e,stroke:#b8a13c,color:#000000
  classDef good fill:#4f9a68,stroke:#357049,color:#ffffff
  classDef bad fill:#c94f4f,stroke:#8f3636,color:#ffffff
```

Solid arrow = live path. **Dashed arrow = planned, or a rule/annotation** rather than a
call. Purple dashed nodes are designed but not built.

## Relation to the rest of `docs/`

The SAD is the **navigable synthesis**. Authoritative detail stays where it lives:

```mermaid
graph LR
  sad[docs/sad<br/>arc42 and C4 synthesis]:::host
  arch[docs/architecture<br/>per-surface design]:::comp
  con[docs/contracts<br/>frozen API spec]:::comp
  adr[docs/decisions<br/>ADR 001-032]:::comp
  ops[docs/ops<br/>runbooks]:::comp
  code[(backend / web / mobile<br/>source of truth)]:::store

  sad --> arch
  sad --> con
  sad --> adr
  sad --> ops
  arch --> code
  con --> code
  adr --> code
  ops --> code

  classDef host fill:#1168bd,stroke:#0b4884,color:#ffffff
  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef store fill:#438dd5,stroke:#2e6295,color:#ffffff
```

**Rule:** change a surface → update its owning doc in the same PR; update the SAD only
when a *structural* fact changes (a container, a component boundary, a quality goal).
