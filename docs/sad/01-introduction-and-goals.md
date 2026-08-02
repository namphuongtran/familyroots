# 1. Introduction and Goals

## 1.1 What the system does

Lets Vietnamese clans (*dòng họ*) maintain an accurate, shared family tree across web
and mobile, with role-based collaboration, full auditability, and strict per-clan data
isolation so many clans coexist in one deployment.

## 1.2 Requirements overview

| # | Capability | Owner surface |
|---|---|---|
| R1 | Clan-scoped person records with rich Vietnamese naming + historical dates | `person` |
| R2 | Genealogy edges: marriage (incl. đa thê), parent-child | `relationship` |
| R3 | Tree read: descendants, ancestors, focus view, computed **đời** | `tree` |
| R4 | Multi-clan membership + clan switching | `clan`, `me` |
| R5 | RBAC: `viewer < editor < admin`, plus platform `super_admin` | `auth`, `clan` |
| R6 | Documents (photos/files), events, giỗ anniversary reminders | `document`, `event` |
| R7 | Identity claims — link an auth user to a person record | `person` |
| R8 | Clan export — lossless JSON archive + GEDCOM 5.5.1 interop | `export` |
| R9 | Audit trail on every mutation | cross-cutting |
| R10 | 4 locales: `vi` (default), `en`, `zh`, `fr` | cross-cutting |

## 1.3 Quality goals (top 5, ranked)

```mermaid
graph TB
  q1[1. Tenant isolation<br/>no clan sees another clan's data]:::host
  q2[2. Correctness<br/>genealogy invariants and đời authority]:::host
  q3[3. Auditability<br/>no business change without its audit row]:::host
  q4[4. Contract stability<br/>3 clients bind one frozen REST spec]:::host
  q5[5. Evolvability<br/>machine-enforced layer boundaries]:::host

  m1[app-layer filters plus RLS layer-2<br/>ADR-002, ADR-008]:::comp
  m2[domain aggregates, DB backstops, OCC<br/>ADR-023, ADR-025, ADR-027, ADR-017]:::comp
  m3[in-transaction domain events<br/>ADR-014]:::comp
  m4[envelope, HistoricalDate, cursor<br/>ADR-010, ADR-011]:::comp
  m5[import-linter ratchet<br/>ADR-013]:::comp

  q1 --> q2
  q2 --> q3
  q3 --> q4
  q4 --> q5
  q1 -.->|realised by| m1
  q2 -.->|realised by| m2
  q3 -.->|realised by| m3
  q4 -.->|realised by| m4
  q5 -.->|realised by| m5

  classDef host fill:#1168bd,stroke:#0b4884,color:#ffffff
  classDef comp fill:#85bbf0,stroke:#5d82a8,color:#000000
```

Detail: [10-quality-requirements.md](10-quality-requirements.md).

## 1.4 Stakeholders

| Role | Cares about |
|---|---|
| Clan admin | Membership approval, roles, accuracy, export |
| Clan editor / viewer | Adding relatives; browsing the tree; giỗ reminders |
| Platform super-admin | Cross-clan observability, audit log, clan suspension |
| Backend / web / mobile devs | Layer rules, frozen contracts, test harness |
| Operator | Deploys, migrations, backups, incidents |
