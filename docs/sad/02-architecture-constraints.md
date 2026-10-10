# 2. Architecture Constraints

## 2.1 Technical

| Constraint | Consequence |
|---|---|
| Python 3.14 · FastAPI · SQLAlchemy async (psycopg v3) · Pydantic v2 | Backend stack fixed |
| PostgreSQL, **single schema**, `clan_id` isolation | No per-tenant schema/DB (ADR-002) |
| Alembic, one **linear** chain, revision id ≤ 32 chars | No migration branches |
| Next.js 16 · React 19 · TypeScript strict | Web stack fixed |
| Flutter · Dart · BLoC · Dio/Retrofit · get_it | Mobile stack fixed |
| Supabase Auth issues JWTs; backend validates via JWKS | Backend never mints tokens |
| Supabase Storage, one bucket, path isolation `clans/{clan_id}/…` | No per-clan bucket |
| Vercel (backend + web, functions in `sin1`) + one Supabase project (database, auth, storage; `ap-southeast-1`), all in Singapore, since 2026-10-10 (ADR-065, ADR-066) | Latency budget set by region. Render is retired |
| Backend runs as Vercel Functions on Hobby: no long-running process, one region, 300 s per request, 4.5 MB request body, crons at most daily and anywhere in their hour | Scheduled jobs run from Vercel Cron, not in-process; DB through Supavisor's transaction pooler with `NullPool`; uploads capped at 4 MB (ADR-065) |
| Production migrations run from CI (`backend-ci.yml` deploy job), before the deploy | A migration must stay compatible with the code already live ([../ops/migrations.md](../ops/migrations.md)) |

## 2.2 Organizational / process

- **Docs-with-code:** API change → update `docs/contracts/*` in the same PR;
  architectural change → new ADR in the same PR.
- **Quality gate before "done"** (backend): `pytest -q` · `ruff check .` ·
  `ruff format --check .` · `mypy app/ tests/` · `lint-imports`.
- Integration tests run against a **real Postgres**, never mocks (ADR-016).
- `main` → production directly. **No staging gate.**

## 2.3 Conventions — hard rules

```mermaid
graph LR
  n1[Bypass clan isolation]:::bad
  n2[Import FastAPI, SQLAlchemy or Pydantic<br/>into backend domain]:::bad
  n3[Commit secrets or plain .env]:::bad
  n4[Treat in-process events<br/>as durable integration events]:::bad
  n5[Commit a session outside UoW<br/>except sanctioned background jobs]:::bad

  e1[two-sided isolation tests plus RLS]:::good
  e2[import-linter contracts]:::good
  e3[gitleaks and pr-checks.yml]:::good
  e4[ADR-004 marked deferred]:::good
  e5[code review plus import-linter fence]:::good

  n1 -->|caught by| e1
  n2 -->|caught by| e2
  n3 -->|caught by| e3
  n4 -->|caught by| e4
  n5 -->|caught by| e5

  classDef bad fill:#c94f4f,stroke:#8f3636,color:#ffffff
  classDef good fill:#4f9a68,stroke:#357049,color:#ffffff
```

Layer dependency rule (all three codebases share this shape):

```mermaid
graph LR
  p[presentation / api]:::comp
  a[application]:::comp
  d[domain]:::core
  i[infrastructure]:::comp

  p --> a
  a --> d
  i -->|implements ports| d
  a -.->|never| i
  d -.->|never| i

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef core fill:#e8a33d,stroke:#a9741f,color:#000000
```
