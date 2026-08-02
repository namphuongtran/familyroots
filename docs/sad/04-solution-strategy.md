# 4. Solution Strategy

## 4.1 Goal → approach

| Goal | Approach | Ref |
|---|---|---|
| Tenant isolation | App-layer `clan_id` filter (primary) + Postgres RLS (layer-2) | ADR-002, ADR-008 |
| Domain correctness | DDD aggregates + DB backstop constraints/triggers + OCC `version` | ADR-023/025, ADR-017 |
| Auditability | Domain events dispatched **inside** the write transaction | ADR-014 |
| One contract, 3 clients | REST-first, frozen envelope + `HistoricalDate` + cursor pagination | ADR-003/010/011 |
| Evolvability | Hexagonal layers, machine-enforced by import-linter ratchet | ADR-001, ADR-013 |
| Read performance | CQRS query ports + recursive-CTE tree functions, bulk-fetch (no N+1) | ADR-001 |
| Test confidence | Real-Postgres integration harness, two-sided isolation tests | ADR-016 |

## 4.2 Decomposition strategy

Vertical layering, horizontal context slices — one folder per context in every layer.

```mermaid
graph TB
  subgraph layers[Layering - vertical]
    api[api/v1<br/>thin routes]:::comp
    app[application<br/>handlers]:::comp
    dom[domain<br/>aggregates and ports]:::core
    uow[UnitOfWork]:::comp
    inf[infrastructure<br/>adapters]:::comp
  end

  subgraph contexts[Contexts - horizontal slices]
    ctx[person · relationship · tree · clan · branch<br/>document · event · auth · me<br/>platform_admin · export]:::comp
  end

  api --> app
  app --> dom
  app --> uow
  uow --> inf
  inf -.->|implements ports| dom
  layers -.->|one folder per context<br/>in every layer| contexts

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef core fill:#e8a33d,stroke:#a9741f,color:#000000
```

**Write side** → aggregate + repository port + UoW + domain events.
**Read side** → CQRS query port, may join across aggregates, no aggregate load.

## 4.3 Key technology choices

```mermaid
graph LR
  web[web<br/>Next.js 16, React 19<br/>TanStack Query and Zustand]:::host
  mob[mobile<br/>Flutter, BLoC<br/>get_it, Dio/Retrofit]:::host
  api[backend<br/>FastAPI, Pydantic v2]:::host
  orm[SQLAlchemy async<br/>psycopg v3]:::comp
  db[(PostgreSQL 18<br/>single schema)]:::store

  web -->|REST /api/v1<br/>JWT and X-Current-Clan-Id| api
  mob -->|REST /api/v1<br/>JWT and X-Current-Clan-Id| api
  api --> orm
  orm --> db

  classDef host fill:#1168bd,stroke:#0b4884,color:#ffffff
  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef store fill:#438dd5,stroke:#2e6295,color:#ffffff
```

## 4.4 Deliberately deferred

- **Redis event bus + worker service** (ADR-004/005) — in-process
  `InMemoryEventDispatcher` today; not a durable integration bus.
- **Async/PDF export** — exports are synchronous and request-scoped.
- **Staging environment** — `main` is production.
