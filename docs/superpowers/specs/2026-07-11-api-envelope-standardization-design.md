# API Success-Envelope Standardization (F-1) — Design Spec

**Date:** 2026-07-11
**Branch:** `feat/api-envelope-standardization` (off `main` @ 5b13851)
**Why:** the success-response contract is inconsistent — 19/82 routes don't follow the `{"data": ...}`
convention, and **three different pagination schemes coexist**. This is a client-facing contract
change; the window is now, before the (deferred) frontend is built against a stable shape.

**Owner decisions (2026-07-11):**
- **Auth token responses wrap in `{"data": ...}`** (login/register/onboard/refresh) — one rule
  everywhere, no client special-casing.
- **Pagination is unified** to the single existing cursor scheme (`meta: {cursor, has_more, limit}`
  via `app/core/pagination.py`), including converting the claims offset scheme and fixing `GET /persons`.

## Canonical contract

1. **Every 2xx JSON body is `{"data": <payload>}`.** `<payload>` is the object, list, or
   `{"message": ...}` the route produces.
2. **List endpoints add `"meta"`**: `{"data": [...], "meta": {"cursor": str|null, "has_more": bool, "limit": int}}`
   — always the cursor scheme from `build_page()`/`paginate_query()` (ASC on `(created_at, id)`).
3. **204 No Content** responses have no body (unchanged).
4. **Non-data adjuncts go inside `meta`**, never as top-level siblings of `data`
   (e.g. batch partial-failures, advisory warnings).
5. **`GET /health` is exempt** — it is an ops/liveness probe (bare status dict), by industry convention
   not part of the API envelope. Explicitly out of scope.
6. **No response-envelope middleware.** Keep the codebase's explicit per-route `{"data": ...}` pattern
   (middleware can't tell enveloped-from-not, can't supply pagination meta, and breaks 204/health/response_model).

## Per-route changes (the 19 non-conforming routes)

### Bare model → wrap in `{"data": <model>.model_dump()}` (drop `response_model`, return `dict[str, Any]`)
| Route | File | After |
|---|---|---|
| POST /auth/register | `auth.py:41` | `{"data": RegisterResponse...}` |
| POST /auth/onboard | `auth.py:57` | `{"data": RegisterResponse...}` |
| POST /auth/login | `auth.py:75` | `{"data": LoginResponse...}` (includes nested `user`) |
| POST /persons/{id}/claim | `persons.py:426` | `{"data": IdentityClaimResponse...}` |
| POST /clans/{cid}/claims/{id}/approve | `claims.py:70` | `{"data": IdentityClaimResponse...}` |
| POST /clans/{cid}/claims/{id}/reject | `claims.py:93` | `{"data": IdentityClaimResponse...}` |
| POST /clans/{cid}/claims/members/{uid}/prelink | `claims.py:139` | `{"data": ...}` (keep 201) |
| POST /clans/{cid}/invitations | `invitations.py` | `{"data": InvitationCreatedResponse...}` (keep 201) |
| POST /invitations/{token}/accept | `invitations.py` | `{"data": InvitationAcceptedResponse...}` |

### Bare message → wrap
| Route | File | After |
|---|---|---|
| POST /auth/logout | `auth.py:83` | `{"data": {"message": ...}}` |

### Auth tokens (flat) → wrap
| Route | After |
|---|---|
| POST /auth/refresh | `{"data": {"access_token", "refresh_token", "expires_in"}}` (tokens-only by design; `login` is the one that carries `user`) |

### me/* custom → wrap
| Route | Before | After |
|---|---|---|
| GET /me/clans | `{"clans": [...], "count": n}` | `{"data": [...clans...], "meta": {"count": n}}` (list → `data`; `count` is an adjunct → `meta`) |
| POST /me/clans/{id}/select | flat `{clan_id, clan_name, clan_slug, role, message}` | `{"data": {clan_id, clan_name, clan_slug, role, message}}` |

### Adjunct siblings → move into `meta`
| Route | Before | After |
|---|---|---|
| POST /persons/batch | `{"data": [...], "errors": [...]}` | `{"data": [...], "meta": {"errors": [...]}}` |
| POST /relationships/parent-child | `{"data": {...}, "warning"?: ...}` | `{"data": {...}, "meta": {"warning": ...}}` (omit `meta` or `meta.warning` when no warning) |

### Pagination unification → cursor `meta`
| Route | Before | After |
|---|---|---|
| GET /persons | `{"data": [...], "total": n}` (accepts `cursor`, never returns one) | `{"data": [...], "meta": {cursor, has_more, limit}}` via `paginate_query`/`build_page`; drop the bare `total`; params become `cursor` + `limit` |
| GET /claims | `{"data": {items, total, page, page_size}}` (offset) | `{"data": [...], "meta": {cursor, has_more, limit}}`; params `page/page_size` → `cursor/limit` |
| GET /clans/{cid}/claims | **bare** `{items, total, page, page_size}` (no `data`!) | `{"data": [...], "meta": {cursor, has_more, limit}}`; params `page/page_size` → `cursor/limit` |

**Claims pagination conversion detail:** `SqlAlchemyClaimQueryPort.list_clan_claims` / `list_user_claims`
move from offset (`page/page_size`, `created_at DESC`) to cursor (`paginate_query(query, ClaimModel,
cursor, limit)` + `build_page`, `created_at ASC`). `IdentityClaimPaginatedResponse{items,total,page,page_size}`
is **retired**; the handlers return `{"data": [IdentityClaimResponse...], "meta": {...}}` (or a typed
`Page[IdentityClaimResponse]` mirroring the platform_admin `Page`/`PageMeta` pattern). Ordering flips to
ASC (oldest-first), consistent with every other cursor endpoint. The `?fields=` sparse-filter on the
admin claims list is preserved (applied to the `data` list).

## Schema / handler impact

- Retire `IdentityClaimPaginatedResponse`; claim list handlers return the cursor `data`+`meta` shape.
- `RegisterResponse` / `LoginResponse` / `InvitationCreatedResponse` / `InvitationAcceptedResponse` /
  `IdentityClaimResponse` stay as the **inner** payload models (serialized under `data`); the routes stop
  using them as `response_model` and return `dict[str, Any]` (matching every other enveloped route).
- me handlers: `list_clans` returns list + count-in-meta; `select_clan` returns the object (route wraps).

## Contract docs

Update `docs/contracts/`: add a short **"Response envelope"** section (canonical rule + pagination) to
`docs/contracts/README.md`, and correct the per-surface docs (`rest-auth-api.md`, `rest-me-api.md`,
`rest-persons-api.md`, `rest-claims-api.md`, `rest-tree-api.md`, invitations) to show the `{"data": ...}` /
`{"data": [...], "meta": {...}}` shapes. This is the canonical record the future frontend builds against.

## Testing

This touches many existing tests that assert the OLD shapes (across auth, me, persons, claims,
invitations, relationships integration + unit tests). Each task updates the tests for the routers it
changes; the **full suite gate is the safety net** for missed assertions (per the SP-2B lesson: run the
whole suite, not just the task's files). New/updated assertions verify the canonical shape:
- Enveloped: top-level keys are exactly `{"data"}` (or `{"data","meta"}` for lists).
- Auth: login/register/refresh bodies are `{"data": {...}}`; login's `data` carries `user`.
- Pagination: claims + persons lists return `data` + `meta{cursor,has_more,limit}`; a second page via the
  returned `cursor` advances correctly (real-DB).
- Adjuncts: batch partial-failure surfaces under `meta.errors`; parent-child advisory under `meta.warning`.
- `GET /health` unchanged (bare status).

Full gate: `uv run pytest`, `uvx ruff check .`, `uvx ruff format --check .`, `uv run mypy app/ tests/`,
`uv run lint-imports`.

## Decomposition (execution)

One PR, tasks grouped by router so each is independently reviewable and touches a bounded test surface,
and no route is broken twice:
1. **auth** — register/onboard/login/refresh/logout → `{data}`.
2. **me** — clans (list+count→meta) / select → `{data}`.
3. **claims** — approve/reject/prelink wrap + **both list endpoints → cursor `data`+`meta`** (retire the
   offset scheme) + preserve `?fields=`.
4. **invitations** — create/accept → `{data}`.
5. **persons + relationships** — persons list → cursor `meta` (drop bare `total`), batch `errors`→`meta`,
   `/claim` wrap; parent-child `warning`→`meta`.
6. **contract docs** — README envelope section + per-surface shape corrections.

## Out of scope

- `GET /health` (exempt). Response-envelope middleware (rejected — see rule 6). A DESC/newest-first cursor
  variant of the pagination helper (all cursor endpoints stay ASC). The 63 already-conforming routes.
- Any non-envelope behavior change (auth logic, claim logic, etc. unchanged — only the response shape).
