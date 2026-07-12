# Contracts Index

This folder is the canonical home for public API and event contract documentation.

## Response envelope

Canonical rule for every REST endpoint under `/api/v1` (backend F-1, standardized
across all routers):

- **Every 2xx JSON body is `{"data": <payload>}`.** `<payload>` may be an object
  (single resource, action result, `{"message": ...}`) or an array (a list that
  isn't cursor-paginated, e.g. `GET /persons/{id}/marriages`).
- **List endpoints** (cursor-paginated) additionally return a top-level `meta`:
  ```json
  {
    "data": [ ... ],
    "meta": { "cursor": "opaque-string-or-null", "has_more": true, "limit": 20 }
  }
  ```
  - `cursor` is **opaque** — clients must not parse or construct it, only pass the
    value returned from the previous page back as the `cursor` query param to fetch
    the next page.
  - `has_more` indicates whether another page exists; `cursor` is `null` when
    `has_more` is `false`.
  - `limit` echoes the effective page size (request `limit` query param, or its
    default/cap).
  - This cursor scheme is the **only** pagination contract — there is no
    `page`/`page_size`/`total`/`next_cursor` variant anywhere in the API.
- **204 No Content** responses (e.g. revoke/unlink/cancel) have **no body**.
- **Non-data adjuncts live under `meta`**, never mixed into `data`:
  - `meta.errors` — per-item failures in a batch/partial-failure operation
    (`data` still holds the successfully-processed items).
  - `meta.warning` — non-fatal advisories about the request that succeeded anyway
    (e.g. a parent-child link created despite an unusual age gap).
  - `meta.count` — a simple count alongside a non-cursor list.
- **`GET /health` is exempt** — it's an ops/liveness probe, not a data endpoint,
  and returns a bare status dict, not an envelope.
- **Error envelope** (unchanged, already standard): every non-2xx JSON body is
  ```json
  { "error": { "code": "...", "message": "...", "detail": { ... } } }
  ```

## HistoricalDate (canonical date shape)

Every genealogical date in a response (persons `birth_date`/`death_date`, events
`event_date`, marriages `marriage_date`/`divorce_date`, all tree nodes) is an object,
never a bare string:

```json
{
  "date": "1750-01-01",              // ISO date or null — best-known point (sorting, anniversaries)
  "precision": "circa",              // exact | year | month | circa | unknown
  "display": "khoảng 1750",          // human text; render this when precision != "exact"
  "lunar": "15/08 Nhâm Tý"           // display-only lunar string or null
}
```

Clients render `date` when `precision == "exact"`, otherwise `display` (falling back
to `date`). Write DTOs accept the scalar `*_date` plus optional `*_precision`
(default `"exact"`) and `*_display`. Exceptions that stay scalar dates: document
`taken_date`, tree `SpouseNode.marriage_date`/`divorce_date`, `/events/upcoming`
`next_occurrence` (derived). See ADR-011.

## Rules
- One file per public contract surface.
- Every contract file must state owner, consumers, schema, and versioning rules.
- Additive changes are preferred.
- Breaking changes must be paired with a migration strategy and an ADR.
- Keep these docs aligned with backend routes and client expectations.

## Current Contracts
- [rest-auth-api.md](rest-auth-api.md)
- [rest-me-api.md](rest-me-api.md)
- [rest-clans-api.md](rest-clans-api.md)
- [rest-persons-api.md](rest-persons-api.md)
- [rest-relationships-api.md](rest-relationships-api.md)
- [rest-branches-api.md](rest-branches-api.md)
- [rest-tree-api.md](rest-tree-api.md)
- [tree-focus.md](tree-focus.md)
- [rest-documents-api.md](rest-documents-api.md)
- [rest-events-api.md](rest-events-api.md)
- [rest-claims-api.md](rest-claims-api.md)
- [rest-invitations-api.md](rest-invitations-api.md)
- [rest-platform-admin-api.md](rest-platform-admin-api.md)
- [rest-notifications-api.md](rest-notifications-api.md)
- [push-notifications.md](push-notifications.md) — FCM token lifecycle, notification types actually sent, payload shapes
- [error-codes.md](error-codes.md) — machine-readable error-code catalog
- [frontend-integration-guide.md](frontend-integration-guide.md) — cross-cutting client integration behavior
- [domain-events-audit.md](domain-events-audit.md)
- [domain-events-catalog.md](domain-events-catalog.md)
- [redis-domain-events.md](redis-domain-events.md) — ⚠️ design target only, nothing implemented (see ADR-004)

## Maintenance Notes
- Keep route names consistent with backend router prefixes.
- Update consumers when a contract changes.
- Add versioned files if a breaking API branch is introduced.
