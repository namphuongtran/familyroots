# Typed OpenAPI responses for tree + platform-admin

**Date:** 2026-07-18
**Status:** Approved — ready for implementation plan
**Branch:** `feat/typed-responses-tree-platform-admin`

## Problem

Commit `4b904a6` ("feat(api): typed OpenAPI response envelopes") annotated every
v1 router with documentation-only `responses=` envelopes so client codegen
(openapi-typescript, Dio/Retrofit) gets real types instead of
`Record<string, unknown>`. Two routers were deliberately deferred as "follow-up
pending typed read models":

- `app/api/v1/tree.py` (5 routes)
- `app/api/v1/platform_admin.py` (6 routes)

They remain the only v1 2xx responses the generated OpenAPI describes as bare
untyped objects. This spec closes that gap.

## Approach (settled house pattern — no deviation)

Every route declares its success envelope via the route's `responses=` argument
using the helpers in `app/schemas/envelope.py` (`ok`, `created`, `page`,
`ok_list`, `ok_message`). This is **documentation-only** — never
`response_model=`, because runtime re-validation would break the sparse
`fields=`/`profile=` subset responses (the reason F-1 dropped `response_model`).
Routes keep building their bodies exactly as they do today. When a route supports
a `profile=` subset, the documented schema describes the **full/widest** shape and
clients treat narrower profiles as subsets of it.

**Zero runtime behavior change.** No new endpoints, no `response_model=`, no change
to `profile=`/pagination behavior, no migration.

### Wire-typed schemas

The handlers serialize UUIDs via `str(...)` and datetimes via `.isoformat()`, so
the JSON wire carries **strings**, not `uuid.UUID`/`datetime`. New response
schemas are typed to that wire (`str` / `str | None`), consistent with the rest
of `app/schemas/`. They are Pydantic v2 models (`app/schemas/` is the response-DTO
layer); the domain read-model dataclasses in
`app/domain/platform_admin/query_port.py` stay framework-agnostic and are **not**
reused here (they carry `uuid.UUID`/`datetime`, not the wire shape).

## Component changes

### 1. Platform-admin — new file `app/schemas/platform_admin.py`

Pydantic response models mirroring the exact wire shapes emitted by
`PlatformAdminQueryHandler` (`app/application/platform_admin/handlers.py`):

| Schema | Wire shape (from handler) | Route | Helper |
|---|---|---|---|
| `ClanSummaryResponse` | `id, name, slug, is_active, created_at: str \| None` | `GET /platform/clans` | `page(...)` |
| `ClanStatsResponse` | `total_members, total_users` | (nested) | — |
| `ClanDetailResponse` | `id, name, slug, is_active, description: str\|None, origin_place: str\|None, created_at: str\|None, stats: ClanStatsResponse` | `GET /platform/clans/{clan_id}` | `ok(...)` |
| `ClanStatusResponse` | `is_active: bool, clan_id: str` | `POST /platform/clans/{clan_id}/suspend`, `.../reactivate` (both 200) | `ok(...)` |
| `PlatformMetricsResponse` | `total_clans, active_clans, suspended_clans, total_members, total_users` (all `int`) | `GET /platform/metrics` | `ok(...)` |
| `AuditLogEntryResponse` | `id, clan_id: str\|None, actor_id, actor_role, action, resource_type, resource_id: str\|None, created_at: str\|None` | `GET /platform/audit-log` | `page(...)` |

Then wire each route in `app/api/v1/platform_admin.py` with the matching
`responses=` argument. No handler/route body changes.

### 2. Tree — reuse existing schemas + two new ones in `app/schemas/tree.py`

| Route | Documented schema | Notes |
|---|---|---|
| `GET /tree/focus/{person_id}` | `ok(FocusView)` | Route already coerces to `FocusView` at runtime — trivial. |
| `GET /tree` (full) | `ok(TreeResponse)` | Existing `TreeResponse{tree: TreeNode, total_persons, total_generations}`; handler returns exactly these three keys. |
| `GET /tree/subtree/{person_id}` | `ok(TreeResponse)` | Same shape as full. |
| `GET /tree/ancestors/{person_id}` | `ok_list(TreeNodeDetail)` | Judgment call ① — see below. |
| `GET /tree/path` | `ok(RelationshipPathResponse)` | Judgment call ② — new schemas below. |

**New schemas in `app/schemas/tree.py`:**

```python
class PathStep(BaseModel):
    person_id: str
    full_name: str
    gender: str
    edge_type: str | None = None
    avatar_url: str | None = None

class RelationshipPathResponse(BaseModel):
    path: list[PathStep] = []
    description: str | None = None
    found: bool = False
```

`PathStep` matches the handler's step shape **after** it strips `birth_date` /
`birth_date_precision` (those thread through only for the kinship descriptor's age
logic and were never exposed).

## Judgment calls (approved)

**① Ancestors documented schema → `TreeNodeDetail` (reuse, not a dedicated schema).**
The `full` profile returns a lean node (`id, full_name, gender, birth_date,
death_date, avatar_url, generation, depth`); `summary`/`detail` coerce to
`TreeNodeSummary`/`TreeNodeDetail`. No profile is a strict superset of the others,
but `TreeNodeDetail` is the widest — every profile's fields are a subset of it
(the fields a given profile omits simply default in the schema). Documenting
`ok_list(TreeNodeDetail)` follows the house "document the full shape, sparse is a
subset" convention without introducing a fourth near-duplicate node schema.

**② Path response → new `RelationshipPathResponse` + `PathStep`.**
No existing schema fits; the shape is genuinely new. Typed to the wire.

## Testing

Extend `tests/unit/api/test_openapi_typed_responses.py` (unit; asserts on the
generated OpenAPI `$ref`s — no runtime change to assert):

- `GET /tree` 200 → `Envelope` + `TreeResponse`
- `GET /tree/ancestors/{person_id}` 200 → `Envelope` + `TreeNodeDetail` (list)
- `GET /tree/path` 200 → `Envelope` + `RelationshipPathResponse`
- `GET /platform/clans` 200 → `PageEnvelope` + `ClanSummaryResponse`
- `GET /platform/clans/{clan_id}` 200 → `Envelope` + `ClanDetailResponse`
- `GET /platform/metrics` 200 → `Envelope` + `PlatformMetricsResponse`

Remove the "tree/platform-admin read models are follow-up" caveat from the module
docstring once covered.

The existing route/integration tests already pin the actual response **bodies**;
since this change is documentation-only, they must continue to pass unchanged —
that is the negative control proving no behavior changed.

## Docs

- `docs/contracts/README.md` — remove the note that tree/platform-admin stay
  untyped (added by `4b904a6`).

## Definition of done

- All 11 routes across the two routers carry a typed `responses=` envelope.
- `create_app().openapi()` shows named schemas (not bare objects) for every one.
- Full gate green: `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.
- No existing test modified except the OpenAPI-shape test (additions only) — proof of zero behavior change.
