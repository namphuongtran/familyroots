# ADR-010: Canonical Success Envelope + Cursor-Only Pagination

## Status
Accepted (2026-07-11, "F-1" standardization — shipped)

## Context
Success bodies had grown inconsistent across routers (bare objects, bare lists,
`next_cursor`/`has_more` at top level, a `total` on persons, offset pagination on
claims). Errors were already standardized (`{"error": {...}}`), successes were not.
The frontend was deliberately deferred, so this was the last cheap window for a
breaking response reshape.

## Decision
- Every 2xx JSON body is `{"data": <payload>}`; list endpoints add
  `"meta": {"cursor", "has_more", "limit"}`; 204 has no body; `/health` is exempt.
- Adjunct information lives under `meta` (`meta.errors` for batch partial failures,
  `meta.warning` for advisories, `meta.count` for non-cursor lists) — never mixed
  into `data`.
- **One pagination scheme**: opaque ASC cursors over `(created_at, id)` (or an
  order-matched composite, e.g. `(full_name, id)` for name-ordered person lists).
  No offset, no `page/total`, no DESC variant. Claims migrated offset→cursor;
  persons dropped `total`.
- Auth token responses are wrapped in `data` like everything else.

## Consequences
Easier: one client-side unwrap rule; pagination handled once; adjuncts can be added
non-breakingly via `meta`.
Harder: was a breaking change (accepted — the pre-envelope web scaffold must adopt
the new shapes); no total counts (a count endpoint/meta.count is the escape hatch);
typed OpenAPI `response_model` (`Envelope[T]`) was deliberately deferred until the
frontend commits to codegen — dynamic person/tree reads can't be statically typed.

Spec: `docs/contracts/README.md#response-envelope`.
