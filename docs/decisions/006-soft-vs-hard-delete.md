# ADR-006: Selective Soft-Delete by Aggregate

## Status
Accepted.

> **Update (2026-07-12):** The `documents` row of the table below is
> **superseded by [ADR-019](019-document-soft-delete-purge.md)**: documents
> now soft-delete (`is_deleted`/`deleted_at`/`deleted_by`, migration
> `016_document_soft_delete`) with a `restore` endpoint and a
> `DOCUMENT_RETENTION_DAYS` purge job, instead of hard-deleting on `DELETE`.
> `Event` and `Branch` remain hard-deleted as described here; only `Document`
> moved.

> **Amendment (2026-08-22, ADR-051, seed S-055):** the 2026-07-02 update below is
> **amended, not withdrawn as a whole, and its text is left exactly as written.** Its
> first clause — "soft-deleting a person will also soft-delete its edges" — is
> **superseded**: no cascade is built and none will be.
> [ADR-051](051-edge-visibility-derived-not-cascaded.md) decided that an edge's
> visibility is **derived on read**, not stored on the edge row. An edge is visible when
> its own `is_deleted` is `false` **and** neither endpoint person's `is_deleted` is
> `true`. Its second clause — "`restore` re-activates only the edges hidden by that same
> delete" — **stands and is satisfied exactly**, because the person's flag is one of the
> three inputs to the predicate: restoring a person un-hides the edges its delete hid, and
> an edge an admin deleted separately keeps its own flag and stays hidden. Nothing is
> stored to tell the two apart, so nothing can be lost.
> The read filter shipped on 2026-08-22 as seed S-054
> (`backend/app/infrastructure/persistence/person_query_port.py:84`,
> `person_repository.py:274,281`). The five reasons the cascade lost — chiefly that a
> cascading **restore** can be refused by migration 022's `parent_child` guard and left
> half-applied — are in ADR-051 § 4. Two by-id reads still carry half the predicate; that
> is ADR-051 § 8 and seed S-056, and it is not a cascade.

> **Update (2026-07-02):** Person/Marriage/ParentChild FKs use `ON DELETE RESTRICT`
> (persons are never hard-deleted). Soft-deleting a person currently leaves its edges
> live (they are hidden from the clan-scoped tree, which filters `is_deleted=false`,
> but the edge rows remain). **Decision:** soft-deleting a person will also
> soft-delete its edges; `restore` re-activates only the edges hidden by that same
> delete. Behavior change is scheduled (roadmap item E3 from the 2026-07-02 DB
> design review).

## Context
Genealogy records carry historical value and are often referenced by other
records. Accidentally losing a person or a marriage edge is far more damaging than
losing a document or a calendar event. At the same time, soft-delete everywhere
adds query-filter burden and storage growth.

Current behaviour (in `app/domain/`):
- `Person`, `Marriage`, `ParentChild` carry `is_deleted` / `deleted_at` /
  `deleted_by` and are **soft-deleted** (restorable; `Person` exposes `restore()`).
- `Document`, `Event`, `Branch` are **hard-deleted** by their repositories.

```mermaid
flowchart LR
    subgraph soft["Soft-delete · khôi phục được"]
        P["Person"]
        M["Marriage"]
        PC["ParentChild"]
    end
    subgraph hard["Hard-delete · xóa hẳn"]
        D["Document"]
        E["Event"]
        B["Branch"]
    end
    soft -->|"lõi gia phả · không mất"| keep["is_deleted = true<br/>restore() được"]
    hard -->|"tái tạo được"| gone["xóa khỏi DB<br/>(+ xóa file qua StoragePort)"]

    classDef s fill:#e8f5e9,stroke:#3b6;
    classDef h fill:#ffebee,stroke:#e55;
    class P,M,PC s;
    class D,E,B h;
```

> 🇻🇳 **Tóm tắt:** Dữ liệu lõi gia phả (nhân khẩu và các cạnh huyết thống/hôn nhân)
> **xóa mềm** để có thể khôi phục và truy vết. Dữ liệu phụ trợ (tài liệu, sự kiện,
> chi/phái) **xóa cứng** vì có thể tạo lại; mọi lần xóa đều ghi vào nhật ký audit
> trước khi thực hiện.

## Decision
Apply soft-delete **only** to the core genealogy aggregates whose loss is
irreversible and audit-sensitive — persons and the edges between them. Keep
supporting aggregates (documents, events, branches) on hard-delete, since they are
re-creatable and not part of the irreplaceable lineage graph.

- Soft-delete writes `deleted_by` + `deleted_at` and emits a delete domain event
  for the audit trail; restoration emits a restore event.
- Hard-delete removes the row (and, for documents, the storage object via
  `StoragePort`) and emits a delete domain event for audit before removal.

## Consequences
Easier:
- Lineage data (persons, marriages, parent-child links) is recoverable and never
  silently lost; deletions are attributable via the audit log.
- Supporting tables stay lean without soft-delete filters everywhere.

Harder:
- **Mixed model** — contributors must know which aggregates are soft vs hard; all
  person/edge reads must filter `is_deleted`. The asymmetry is the main cost.
- Hard-deleted documents/events cannot be restored; rely on the audit log for the
  record of what existed.

See the per-aggregate summary in
[Domain Rules](../architecture/domain-rules.md#soft-delete-vs-hard-delete-summary).
