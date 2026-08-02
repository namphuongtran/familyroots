# 6. Runtime View

## 6.1 Login and clan-context selection

```mermaid
graph TB
  s1[1 Client signs in with Supabase Auth]:::comp
  s2[2 JWT issued]:::comp
  d1{3 Email verified}:::dec
  e1[403 email_not_verified · ADR-015]:::bad
  s4[4 GET /api/v1/me/clans with bearer token]:::comp
  s5[5 Backend verifies JWT against JWKS<br/>cached 1h, asyncio-Lock guarded]:::comp
  d2{6 How many approved memberships}:::dec
  z0[Pending-approval screen]:::bad
  z1[Auto-select · no header needed]:::good
  z2[Clan switcher, then<br/>POST /me/clans/id/select]:::good
  s7[7 Client stores the clan id locally]:::comp
  s8[8 Every later call sends X-Current-Clan-Id]:::comp
  d3{9 Member of that clan<br/>and clan is active}:::dec
  e2[403]:::bad
  ok[10 Request proceeds<br/>RLS GUC app.clan_id set for the transaction]:::good

  s1 --> s2
  s2 --> d1
  d1 -->|no| e1
  d1 -->|yes| s4
  s4 --> s5
  s5 --> d2
  d2 -->|none| z0
  d2 -->|exactly one| z1
  d2 -->|several| z2
  z1 --> s7
  z2 --> s7
  s7 --> s8
  s8 --> d3
  d3 -->|no| e2
  d3 -->|yes| ok

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef dec fill:#f5d76e,stroke:#b8a13c,color:#000000
  classDef good fill:#4f9a68,stroke:#357049,color:#ffffff
  classDef bad fill:#c94f4f,stroke:#8f3636,color:#ffffff
```

## 6.2 Write path — create a person (UoW + audit in one transaction)

```mermaid
graph TB
  r1[1 POST /api/v1/persons]:::comp
  r2[2 Authenticate JWT, then require_role EDITOR]:::comp
  r3["3 Handler builds the Person aggregate<br/>invariants plus add_event(PersonCreated)"]:::comp
  r4["4 uow.track(aggregate)"]:::comp
  r5["5 uow.commit() flushes"]:::comp
  r6[6 Collect domain events from tracked aggregates]:::comp
  r7[7 Dispatch in-process · InMemoryEventDispatcher]:::dec
  r8[8 AuditLogHandler writes audit_logs<br/>enriched with IP and UA from RequestMetaMiddleware]:::comp
  r9[9 COMMIT · business row and audit row atomically]:::good
  rb[ROLLBACK everything<br/>no business change without its audit]:::bad
  out[10 201 with the data envelope]:::good

  r1 --> r2
  r2 --> r3
  r3 --> r4
  r4 --> r5
  r5 --> r6
  r6 --> r7
  r7 -->|handler ok| r8
  r7 -->|handler raises| rb
  r8 --> r9
  r9 --> out

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef dec fill:#f5d76e,stroke:#b8a13c,color:#000000
  classDef good fill:#4f9a68,stroke:#357049,color:#ffffff
  classDef bad fill:#c94f4f,stroke:#8f3636,color:#ffffff
```

**Consequence (ADR-014):** audit is guaranteed, but a failing handler fails the write —
accepted coupling. Events are **not** durable integration events.

## 6.3 Read path — full tree

```mermaid
graph TB
  t1[1 GET /api/v1/tree/full with profile]:::comp
  t2[2 Authorise · caller is a member of the clan]:::comp
  t3[3 TreeQueryHandler calls TreeRepository]:::comp
  t4[4 Recursive CTE get_family_tree_flat · clan-scoped]:::store
  t5[5 One bulk edges query]:::store
  t6[6 One bulk spouse query]:::store
  t7[7 One mother-map query]:::store
  t8[8 tree_builder computes the generation map<br/>đời = canonical parent đời plus 1 · ADR-027]:::comp
  t9[9 đa thê grouping by mother_id and spouse_order<br/>pedigree_collapse_ref stubs]:::comp
  t10[10 Serialise HistoricalDate into the envelope]:::comp
  t11[11 200 with the data envelope]:::good
  note[Statement count is CONSTANT<br/>versus clan size and depth]:::good

  t1 --> t2
  t2 --> t3
  t3 --> t4
  t3 --> t5
  t3 --> t6
  t3 --> t7
  t4 --> t8
  t5 --> t8
  t6 --> t8
  t7 --> t8
  t8 --> t9
  t9 --> t10
  t10 --> t11
  t8 -.->|invariant| note

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef store fill:#438dd5,stroke:#2e6295,color:#ffffff
  classDef good fill:#4f9a68,stroke:#357049,color:#ffffff
```

## 6.4 Giỗ (death anniversary) notification job

```mermaid
graph TB
  n1[1 APScheduler fires daily at NOTIFICATION_CRON_HOUR]:::comp
  d1{2 Advisory lock acquired<br/>on one dedicated connection}:::dec
  skip[Another instance owns today · exit]:::bad
  n3[3 Fix a single today clock and thread it through]:::comp
  n4[4 Solar due-dates via next_anniversary SQL<br/>Feb 29 clamps to Feb 28]:::store
  n5[5 Lunar giỗ via lunar_calendar.py<br/>Hồ Ngọc Đức algorithm, 1910 to 2199]:::comp
  n6[6 Build the payload per event]:::comp
  n7[7 Dedup against notification_log<br/>unique dedup key]:::store
  n8[8 Send FCM to clan members tokens]:::comp
  n9[9 Write the notification_log row]:::good
  perr[Roll back that event and continue<br/>one bad row never kills the run]:::bad
  rule[ADR-028 · release the pooled DB connection<br/>before any external I/O]:::good

  n1 --> d1
  d1 -->|no| skip
  d1 -->|yes| n3
  n3 --> n4
  n3 --> n5
  n4 --> n6
  n5 --> n6
  n6 --> n7
  n7 --> n8
  n8 --> n9
  n6 -->|per-event failure| perr
  n8 -.->|constraint| rule

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef store fill:#438dd5,stroke:#2e6295,color:#ffffff
  classDef dec fill:#f5d76e,stroke:#b8a13c,color:#000000
  classDef good fill:#4f9a68,stroke:#357049,color:#ffffff
  classDef bad fill:#c94f4f,stroke:#8f3636,color:#ffffff
```

## 6.5 Document upload

```mermaid
graph TB
  u1[1 POST /api/v1/documents · multipart]:::comp
  u2[2 Authorise EDITOR on the clan]:::comp
  u3[3 Validate size and type]:::comp
  d1{4 SupabaseStorageAdapter writes to<br/>family-roots-files/clans/clan_id}:::dec
  serr[503 or 404 surfaced · never a raw 500]:::bad
  u5[5 Document aggregate, UoW commit, audit row]:::comp
  u6[6 201 with the data envelope and a presigned URL]:::good
  sd[Soft delete sets deleted_at]:::comp
  pg[document_purge job after retention · ADR-019<br/>removes the blob and the row]:::comp

  u1 --> u2
  u2 --> u3
  u3 --> d1
  d1 -->|storage 5xx or missing| serr
  d1 -->|ok| u5
  u5 --> u6
  u6 --> sd
  sd --> pg

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef dec fill:#f5d76e,stroke:#b8a13c,color:#000000
  classDef good fill:#4f9a68,stroke:#357049,color:#ffffff
  classDef bad fill:#c94f4f,stroke:#8f3636,color:#ffffff
```

## 6.6 Clan export

```mermaid
graph TB
  x1[1 GET /api/v1/exports]:::comp
  x2[2 clan_id from X-Current-Clan-Id<br/>plus RequireAdmin on that clan]:::comp
  x3[3 ExportQueryPort · clan-scoped reads only]:::comp
  x4[4a clan_export.py · lossless JSON archive]:::comp
  x5[4b gedcom_export.py · GEDCOM 5.5.1]:::comp
  x6["5 _fold() escapes @ to @@, normalises newlines<br/>and folds at 200 UTF-8 bytes<br/>every CONC and CONT sits at parent level plus 1"]:::comp
  x7[6 File response]:::good

  x1 --> x2
  x2 --> x3
  x3 --> x4
  x3 --> x5
  x5 --> x6
  x4 --> x7
  x6 --> x7

  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
  classDef good fill:#4f9a68,stroke:#357049,color:#ffffff
```

Synchronous and request-scoped — the async worker of ADR-005 is **not** built.

## 6.7 Failure modes

```mermaid
graph LR
  f1[DB OperationalError<br/>outage or pool exhausted]:::dec
  f2[DB ProgrammingError or DataError]:::dec
  f3[Supabase JWKS or update_user unreachable]:::dec
  f4[Storage unavailable]:::dec
  f5[Domain invariant violated]:::dec
  f6[Concurrent write on a stale version]:::dec
  f7[Auth surface probing]:::dec
  f8[Health check cannot reach the DB]:::dec

  r1[503 database_unavailable · ADR-032]:::good
  r2[500 · this is a real bug]:::bad
  r3[503, not 500]:::good
  r4[503 or 404]:::good
  r5[4xx structured error envelope]:::good
  r6[409 conflict · OCC, ADR-017]:::good
  r7[Non-enumerating response<br/>plus 20 rpm per IP · ADR-021]:::good
  r8[503 degraded · Render pulls the instance]:::good

  f1 --> r1
  f2 --> r2
  f3 --> r3
  f4 --> r4
  f5 --> r5
  f6 --> r6
  f7 --> r7
  f8 --> r8

  classDef dec fill:#f5d76e,stroke:#b8a13c,color:#000000
  classDef good fill:#4f9a68,stroke:#357049,color:#ffffff
  classDef bad fill:#c94f4f,stroke:#8f3636,color:#ffffff
```
