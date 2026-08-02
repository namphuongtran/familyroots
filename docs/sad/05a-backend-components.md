# 5.1 Backend — C4 Level 3 (Components) + Level 4 (Code)

`backend/app/` · FastAPI · DDD + CQRS + hexagonal. Layer rules machine-enforced by
`uv run lint-imports` (ADR-013).

## 5.1.1 Component diagram

```mermaid
graph TB
  req([HTTP request]):::person

  subgraph edge[Edge - app/main.py, app/middleware]
    exc[exception handlers<br/>AppError and DomainError to envelope]:::comp
    cors[CORS]:::comp
    lang[LanguageMiddleware<br/>Accept-Language to locale context]:::comp
    senm[SentryMiddleware · optional]:::comp
    meta[RequestMetaMiddleware<br/>IP and UA into a ContextVar for audit]:::comp
    rate[RateLimitMiddleware<br/>/auth and /invitations · 20 rpm per IP]:::comp
  end

  subgraph sec[Security - app/core]
    jwt[security.py<br/>JWKS verify, get_current_user]:::comp
    clan[security.py<br/>get_current_clan_id from X-Current-Clan-Id]:::comp
    perm[permissions.py<br/>require_role, RequireClanRole, super_admin]:::comp
    rls[rls.py<br/>set app.clan_id GUC, familyroots_app role]:::comp
  end

  subgraph apilayer[api/v1 - thin routes]
    router[router.py<br/>auth · me · clans · branches · persons · relationships<br/>tree · documents · events · exports · claims<br/>invitations · platform_admin]:::comp
  end

  subgraph applayer[application/context]
    cmd[commands.py and queries.py]:::comp
    handler[handlers.py<br/>orchestrate ports and UoW]:::comp
  end

  subgraph domlayer[domain/context - pure Python]
    agg[aggregates and value objects]:::core
    port[repository ports]:::core
    evt[domain events]:::core
    val[RelationshipDomainValidator]:::core
  end

  subgraph inflayer[infrastructure]
    dep[dependencies.py<br/>composition root]:::comp
    uow[unit_of_work.py]:::comp
    repo[persistence/*_repository.py<br/>write adapters]:::comp
    qp[persistence/*_query_port.py<br/>CQRS read projections]:::comp
    disp[event_dispatcher.py<br/>InMemoryEventDispatcher]:::comp
    sto[storage/supabase_adapter.py]:::comp
    idp[supabase_identity_provider.py]:::comp
  end

  subgraph svclayer[services - cross-cutting, import-fenced]
    tb[tree_builder.py]:::comp
    lun[lunar_calendar.py]:::comp
    schd[scheduler.py]:::comp
    noti[notification.py]:::comp
    exp[clan_export.py and gedcom_export.py]:::comp
    purge[document_purge.py]:::comp
    desc[relationship_descriptor.py]:::comp
    tr[translator.py]:::comp
  end

  db[(PostgreSQL)]:::store
  audit[AuditLogHandler]:::comp

  req --> exc
  exc --> cors
  cors --> lang
  lang --> senm
  senm --> meta
  meta --> rate
  rate --> router
  router --> jwt
  jwt --> clan
  clan --> perm
  clan --> rls
  perm --> handler
  handler --> cmd
  handler --> agg
  handler --> port
  agg --> evt
  handler --> uow
  dep -.->|wires| handler
  dep -.->|wires| repo
  dep -.->|wires| qp
  dep -.->|wires| uow
  port -.->|implemented by| repo
  uow --> repo
  repo --> db
  handler --> qp
  qp --> db
  uow -->|flush, dispatch, commit| disp
  disp --> audit
  audit --> db
  handler --> sto
  handler --> tb
  handler --> exp
  handler --> desc
  schd --> lun
  schd --> noti
  schd --> db
  purge --> db
  rls --> db
  jwt --> idp
  lang --> tr
  agg --> val

  classDef person fill:#08427b,stroke:#052e56,color:#ffffff
  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef core fill:#e8a33d,stroke:#a9741f,color:#000000
  classDef store fill:#438dd5,stroke:#2e6295,color:#ffffff
```

## 5.1.2 Component responsibilities

| Component | Owns | Rule |
|---|---|---|
| `api/v1/*` | HTTP shape, status codes, DTO in/out | Thin — no business logic |
| `application/*` | Use-case orchestration, transaction scope | Imports domain only |
| `domain/*` | Invariants, aggregates, ports, events | No FastAPI/SQLAlchemy/Pydantic |
| `infrastructure/persistence/*_repository` | Write adapters for domain ports | Clan filter on every read |
| `infrastructure/persistence/*_query_port` | Read projections, cross-aggregate joins | No aggregate hydration |
| `infrastructure/unit_of_work` | flush → collect events → dispatch → commit | Sole commit path for writes |
| `infrastructure/dependencies` | Composition root → FastAPI `Depends` | Only place that wires concretes |
| `services/*` | Tree build, lunar, scheduler, notify, export, purge | Fenced: no api/application/domain/models imports |

## 5.1.3 Bounded contexts (domain map)

```mermaid
graph TB
  clan[clan<br/>tenant boundary]:::core
  person[person<br/>plus IdentityClaim]:::core
  rel[relationship<br/>Marriage and ParentChild]:::core
  branch[branch]:::core
  doc[document]:::core
  ev[event]:::core
  auth[auth]:::core

  tree[tree · read only]:::comp
  me[me · read only]:::comp
  pa[platform_admin · read only]:::comp
  exp[export · read only]:::comp

  clan -->|clan_memberships M:N| person
  clan -->|created_by_clan_id| rel
  clan --> branch
  clan --> doc
  clan --> ev
  branch -->|founder_person_id| person
  doc -->|optional person_id| person
  ev -->|optional person_id| person
  rel -->|person1, person2, parent, child| person
  auth -->|creates clan and membership| clan
  tree -.->|reads| rel
  tree -.->|reads| person
  me -.->|read projection| clan
  pa -.->|read projection| clan
  exp -.->|read projection| clan

  classDef core fill:#e8a33d,stroke:#a9741f,color:#000000
  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
```

Detail: [bounded-contexts.md](../architecture/bounded-contexts.md).

## 5.1.4 C4 Level 4 — code: a write path (`person`)

```mermaid
graph TB
  rt["api/v1/persons.py<br/>create_person with injected uow and handler"]:::comp
  cm[application/person/commands.py<br/>CreatePerson]:::comp
  hd[application/person/handlers.py<br/>PersonCommandHandler.create]:::comp
  ag["domain/person/person.py<br/>Person.create - invariants<br/>add_event(PersonCreated)"]:::core
  pt[domain/person/ports.py<br/>PersonRepository - abstract]:::core
  rp[infrastructure/persistence/person_repository.py<br/>SqlAlchemyPersonRepository]:::comp
  mp[persistence/person_mapper.py<br/>aggregate to ORM row]:::comp
  uw[infrastructure/unit_of_work.py<br/>track, flush, collect, dispatch, commit]:::comp
  ah[AuditLogHandler<br/>writes audit_logs in the same tx]:::comp
  db[(persons and audit_logs)]:::store

  rt --> cm
  cm --> hd
  hd --> ag
  ag --> pt
  hd --> uw
  pt -.->|implemented by| rp
  rp --> mp
  mp --> db
  uw --> rp
  uw --> ah
  ah --> db

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef core fill:#e8a33d,stroke:#a9741f,color:#000000
  classDef store fill:#438dd5,stroke:#2e6295,color:#ffffff
```

Invariants enforced here: OCC `version` (ADR-017), soft-delete rules (ADR-006),
clan membership on referenced persons, `HistoricalDate` precision (ADR-011).

## 5.1.5 C4 Level 4 — code: the tree read path

```mermaid
graph TB
  rt[api/v1/tree.py<br/>GET /tree/full, /focus, /ancestors]:::comp
  qh[application/tree/handlers.py<br/>TreeQueryHandler]:::comp
  tr[persistence/tree_repository.py<br/>SqlAlchemyTreeRepository]:::comp
  cte[SQL get_family_tree_flat<br/>recursive CTE]:::store
  bulk[one edges query, one spouse query<br/>one mother-map query]:::store
  tb[services/tree_builder.py<br/>compute_generation_map for đời<br/>build_descendants_tree, đa thê grouping]:::comp
  out[schemas<br/>HistoricalDate, mother_id, spouse_order<br/>pedigree_collapse_ref]:::comp
  note[Statement count is a small CONSTANT<br/>independent of clan size and depth<br/>pinned by test_tree_query_count_scaling.py]:::good

  rt --> qh
  qh --> tr
  tr --> cte
  tr --> bulk
  tr --> tb
  tb --> out
  tb -.->|invariant| note

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef store fill:#438dd5,stroke:#2e6295,color:#ffffff
  classDef good fill:#4f9a68,stroke:#357049,color:#ffffff
```

đời authority: **con theo đời cha** — thủy tổ = 1, đời = canonical parent's đời + 1
(ADR-027). Detail: [tree-read-model.md](../architecture/tree-read-model.md).

## 5.1.6 Testing components

| Suite | Location | Backing |
|---|---|---|
| unit | `tests/unit/{api,domain,infrastructure}` | dict/row factories, no DB |
| integration | `tests/integration/` | **real Postgres**, full Alembic chain (ADR-016) |
| isolation | `test_cross_clan_edge_guard.py`, RLS phase tests | two-sided: A sees, B does not |
| perf net | `test_tree_query_count_scaling.py`, `test_person_list_scaling.py` | statement-count + index pins |
