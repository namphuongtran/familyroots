# 5.4 Database — C4 Level 3 (Components)

PostgreSQL 18 · **single `public` schema** · isolation by `clan_id` (ADR-002) ·
Alembic single linear chain. Full column reference:
[data-model.md](../architecture/data-model.md).

## 5.4.1 Table groups

```mermaid
graph TB
  subgraph tenancy[Tenancy]
    clans[(clans<br/>slug unique, is_active)]:::store
    ucr[(user_clan_roles<br/>admin, editor, viewer · is_approved)]:::store
    inv[(clan_invitations)]:::store
    cset[(clan_settings)]:::store
    up[(user_profiles<br/>id = Supabase auth user · platform_role)]:::store
  end

  subgraph genealogy[Genealogy core]
    persons[(persons<br/>global row, version for OCC, soft delete)]:::store
    cm[(clan_memberships<br/>M:N person to clan, is_founder)]:::store
    mar[(marriages<br/>created_by_clan_id, spouse_order)]:::store
    pc[(parent_child<br/>created_by_clan_id)]:::store
    ic[(identity_claims)]:::store
  end

  subgraph supporting[Supporting]
    br[(branches)]:::store
    docs[(documents)]:::store
    evs[(events)]:::store
  end

  subgraph opsdata[Ops and cross-clan]
    al[(audit_logs<br/>cross-clan, IP, user agent)]:::store
    nl[(notification_log<br/>dedup key)]:::store
    cr[(change_requests)]:::store
    fcm[(user_fcm_tokens)]:::store
  end

  clans --> ucr
  clans --> inv
  clans --> cset
  clans --> cm
  clans --> br
  clans --> docs
  clans --> evs
  up --> ucr
  up --> fcm
  up --> ic
  up -->|person_id nullable unique| persons
  cm --> persons
  mar --> persons
  pc --> persons
  ic --> persons
  br -->|founder_person_id| persons
  docs -.->|optional person_id| persons
  evs -.->|optional person_id| persons

  classDef store fill:#438dd5,stroke:#2e6295,color:#ffffff
```

## 5.4.2 Isolation mechanism — differs by table

```mermaid
graph TB
  req([Request with X-Current-Clan-Id]):::person
  sys([System job · scheduler, purge, migrations]):::person

  a[clan-owned tables<br/>documents, events, branches<br/>filter clan_id]:::comp
  b[edge tables<br/>marriages, parent_child<br/>filter created_by_clan_id]:::comp
  c[persons<br/>join clan_memberships<br/>created_by_clan_id is write attribution only]:::comp
  rls[RLS layer-2 · ADR-008<br/>role familyroots_app is non-bypass<br/>plus transaction-local app.clan_id GUC]:::good
  bypass[privileged session<br/>bypasses RLS]:::bad
  db[(PostgreSQL)]:::store

  req --> a
  req --> b
  req --> c
  a -->|defence in depth| rls
  b -->|defence in depth| rls
  c -->|defence in depth| rls
  rls --> db
  sys --> bypass
  bypass --> db

  classDef person fill:#08427b,stroke:#052e56,color:#ffffff
  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef store fill:#438dd5,stroke:#2e6295,color:#ffffff
  classDef good fill:#4f9a68,stroke:#357049,color:#ffffff
  classDef bad fill:#c94f4f,stroke:#8f3636,color:#ffffff
```

RLS **ENABLED** on: `documents`, `events`, `branches`, `marriages`, `parent_child`,
`persons` (migrations `002`, `027`, `028`, `029`). Remaining clan-scoped tables roll
out table-by-table. Gated by `RLS_ENABLED` for code-free rollback.
App-layer filtering remains the **primary** guarantee.

## 5.4.3 Invariant backstops in the DB

| Object | Guards |
|---|---|
| `trg_parent_child_integrity` → `parent_child_integrity_guard()` | Graph invariants on edge write (ADR-023) |
| `trg_parent_child_clan_lock` → `parent_child_clan_lock()` | Per-clan edge-write serialization (ADR-025) |
| `idx_parent_child_unique_edge`, `idx_marriages_unique_pair` | No duplicate edges |
| `uq_marriages_spouse_order` | Two-sided per-person `spouse_order` (ADR-029) |
| `uq_clan_memberships_one_founder` | One thủy tổ per clan (ADR-026) |
| `uq_identity_claim_user_pending`, `uq_clan_invitations_pending` | One pending claim / invite |
| `idx_notification_log_dedup` | Idempotent anniversary push |
| `persons.version` + friends | Optimistic concurrency (ADR-017) |
| FK `RESTRICT` on clan delete | ADR-009 |

## 5.4.4 Read-model SQL functions

```mermaid
graph LR
  tr[tree_repository.py]:::comp
  pr[person_repository.py]:::comp

  f1[get_family_tree_flat<br/>recursive CTE, descendants]:::store
  f2[get_ancestors_flat]:::store
  f3[get_children, get_parents, get_spouses]:::store
  f4[find_relationship_path]:::store
  f5[f_unaccent<br/>Vietnamese search normalisation]:::store

  tr --> f1
  tr --> f2
  tr --> f3
  tr --> f4
  pr --> f5

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef store fill:#438dd5,stroke:#2e6295,color:#ffffff
```

## 5.4.5 Performance surfaces

- Keyset/cursor pagination on `(created_at, id)` — `idx_persons_fullname_keyset`.
- Trigram search: `idx_persons_fullname_trgm`, `idx_persons_birthname_trgm`.
- Partial indexes for hot filters: `idx_documents_purge_due`,
  `idx_events_recurring_date`, `idx_user_clan_roles_pending`,
  `idx_change_requests_pending`, `idx_parent_child_parent_clan_live`.
- Clan-scope index pinned by `test_person_list_scaling.py` (`enable_seqscan=off` +
  asserts `idx_clan_memberships_clan`).

## 5.4.6 Lifecycle

```mermaid
graph LR
  dev[alembic revision --autogenerate<br/>env.py imports all app.models]:::comp
  pr[review]:::comp
  deploy[Render preDeployCommand<br/>alembic upgrade head]:::dec
  block[deploy blocked]:::bad
  live[release goes live]:::good
  cron[db-backup.yml · daily 00:15 ICT]:::comp
  dump[pg_dump, gzip, upload to backups bucket<br/>plus rotation]:::store

  dev --> pr
  pr --> deploy
  deploy -->|migration fails| block
  deploy -->|migration ok| live
  cron --> dump

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef store fill:#438dd5,stroke:#2e6295,color:#ffffff
  classDef dec fill:#f5d76e,stroke:#b8a13c,color:#000000
  classDef good fill:#4f9a68,stroke:#357049,color:#ffffff
  classDef bad fill:#c94f4f,stroke:#8f3636,color:#ffffff
```

Soft delete: `persons`, `documents` (+ retention purge, ADR-019), `events` (ADR-022),
edges. Hard delete elsewhere (ADR-006).
