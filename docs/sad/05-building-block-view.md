# 5. Building Block View — C4 Level 2 (Containers)

## 5.1 Container diagram

```mermaid
graph TB
  user([Clan member / super-admin]):::person

  web[web · Vercel<br/>Next.js 16, React 19, TypeScript<br/>port 3000]:::host
  mob[mobile · App Store and Play<br/>Flutter, Dart, BLoC]:::host

  subgraph render[Render - region singapore]
    api[backend<br/>FastAPI, SQLAlchemy async<br/>port 8000 · DDD, CQRS, hexagonal]:::host
    sched[scheduler · in-process<br/>APScheduler, giỗ anniversaries<br/>advisory-locked daily job]:::host
  end

  db[(database<br/>PostgreSQL 18<br/>single schema, RLS layer-2)]:::store
  storage[(Supabase Storage<br/>family-roots-files)]:::ext
  auth[Supabase Auth]:::ext
  fcm[Firebase Cloud Messaging]:::ext
  sentry[Sentry]:::ext
  redis[Redis - planned]:::v2
  worker[Worker - planned]:::v2

  user --> web
  user --> mob
  web -->|REST /api/v1 · JWT<br/>X-Current-Clan-Id · Accept-Language| api
  mob -->|REST /api/v1 · JWT| api
  web -->|login and refresh| auth
  mob -->|login and refresh| auth
  api -->|verify against JWKS| auth
  api -->|SQL over async pool| db
  sched --> db
  sched -->|push| fcm
  api -->|upload and presign| storage
  api -->|errors and traces| sentry
  api -.->|publish| redis
  redis -.->|consume| worker

  classDef person fill:#08427b,stroke:#052e56,color:#ffffff
  classDef host fill:#1168bd,stroke:#0b4884,color:#ffffff
  classDef store fill:#438dd5,stroke:#2e6295,color:#ffffff
  classDef ext fill:#999999,stroke:#6b6b6b,color:#ffffff
  classDef v2 fill:#7b4fa0,stroke:#54356f,color:#ffffff,stroke-dasharray:5 4
```

## 5.2 Container responsibilities

| Container | Responsibility | Must not |
|---|---|---|
| **web** | Browser UX, admin/backoffice, clan switcher, tree render (XYFlow) | Hold business rules; bypass application ports |
| **mobile** | Native UX, offline-ish cache, push receipt | Assemble auth headers ad-hoc |
| **backend** | All business rules, persistence, authz, contracts, export | Leak infra into domain |
| **scheduler** | Daily anniversary scan + FCM fan-out | Write via UoW (sanctioned out-of-band writer) |
| **database** | Canonical state + invariant backstops + RLS | Be reached by any client directly |

## 5.3 Interfaces between containers

```mermaid
graph LR
  h1[Authorization: Bearer JWT]:::comp
  h2[X-Current-Clan-Id: uuid]:::comp
  h3[Accept-Language: vi, en, zh, fr]:::comp

  api[backend /api/v1]:::host

  b1["Success body: data envelope"]:::comp
  b2["Lists add meta: cursor, has_more, limit"]:::comp
  b3[Dates are HistoricalDate objects]:::comp

  h1 --> api
  h2 --> api
  h3 --> api
  api --> b1
  api --> b2
  api --> b3

  classDef host fill:#1168bd,stroke:#0b4884,color:#ffffff
  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
```

Surfaces: `auth · me · clans · branches · persons · relationships · tree · documents ·
events · exports · claims · invitations · platform-admin` (+ `/health`).
Spec: [`docs/contracts/`](../contracts/README.md).

## 5.4 Drill down (C4 Level 3)

```mermaid
graph LR
  l2[L2 Containers<br/>this page]:::host
  b[backend<br/>05a - L3 and L4]:::comp
  w[web<br/>05b - L3]:::comp
  m[mobile<br/>05c - L3]:::comp
  d[database<br/>05d - L3]:::comp

  l2 --> b
  l2 --> w
  l2 --> m
  l2 --> d

  classDef host fill:#1168bd,stroke:#0b4884,color:#ffffff
  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
```

- [05a — backend components (L3) + code (L4)](05a-backend-components.md)
- [05b — web components (L3)](05b-web-components.md)
- [05c — mobile components (L3)](05c-mobile-components.md)
- [05d — database components (L3)](05d-database-components.md)
