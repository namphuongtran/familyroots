# Typed OpenAPI responses — clean-reuse routes (PR-1 of 2)

**Date:** 2026-07-18
**Status:** Approved — ready for implementation plan
**Branch:** `feat/typed-responses-clean-reuse`

## Problem

After #80, tree + platform-admin are typed, but ~32 auxiliary v1 2xx routes still
render as bare untyped objects in the generated OpenAPI (client codegen emits
`Record<string, unknown>`). This is **PR-1 of a 2-PR effort** to close them.

PR-1 covers the **21 routes that reuse an existing response DTO** — no new schemas,
lowest risk, biggest codegen win. PR-2 (separate spec) covers the ~9 routes that
need new schemas or non-canonical-envelope handling (`/auth/refresh`,
`/persons/search`, `/persons/batch`, `/clans/me/users*`, `/me/clans`).
`/exports/clan` (file download, envelope-exempt) and `/health` (infra) are
**excluded from both** — correctly non-JSON-envelope.

## Approach (settled house pattern — identical to #80)

Each route declares its success envelope via documentation-only `responses=`
(`ok`/`page`/`ok_list`/`ok_message`/`created` from `app/schemas/envelope.py`),
**never** `response_model=` (several of these routes support sparse
`fields=`/`include=` subsets — runtime re-validation would break them). Route and
handler bodies are unchanged. **Zero behavior change.**

## Routes and helpers (21)

### Auth (8) — `app/api/v1/auth.py`
| Route | Helper | Reused schema | Body construction |
|---|---|---|---|
| POST /auth/onboard [201] | `created(RegisterResponse)` | `RegisterResponse` | `result.model_dump()` — coherent by construction |
| POST /auth/register [201] | `created(MessageData)` | `MessageData` | hand-built `{"message": ...}` — trivial |
| POST /auth/logout | `ok_message()` | `MessageData` | trivial message |
| POST /auth/forgot-password | `ok_message()` | `MessageData` | trivial message |
| POST /auth/resend-verification | `ok_message()` | `MessageData` | trivial message |
| PATCH /auth/me | `ok_message()` | `MessageData` | trivial message |
| POST /auth/me/fcm-token | `ok_message()` | `MessageData` | trivial message |
| DELETE /auth/me/fcm-token | `ok_message()` | `MessageData` | trivial message |

### Persons sub-resources (6) — `app/api/v1/persons.py`
All list routes support `fields=` sparse filtering; the query port dumps each item
**through** its DTO (`<DTO>.model_validate(row).model_dump()` in
`person_query_port.py`) → coherent by construction.
| Route | Helper | Reused schema |
|---|---|---|
| GET /persons/{id}/documents | `ok_list(DocumentSummary)` | `DocumentSummary` |
| GET /persons/{id}/events | `ok_list(EventResponse)` | `EventResponse` |
| GET /persons/{id}/marriages | `ok_list(MarriageResponse)` | `MarriageResponse` |
| GET /persons/{id}/parent-child | `ok_list(ParentChildResponse)` | `ParentChildResponse` |
| GET /persons/{id}/timeline | `ok_list(TimelineEvent)` | `TimelineEvent` |
| POST /persons/{id}/claim [201] | `created(IdentityClaimResponse)` | `IdentityClaimResponse` |

### Claims (5) — `app/api/v1/claims.py`
List routes dump items through `IdentityClaimResponse.model_validate(c).model_dump()`
(`claim_handlers.py:375,391`); action routes `return {"data": result.model_dump()}`
where `result` is an `IdentityClaimResponse` → all coherent by construction.
| Route | Helper |
|---|---|
| GET /claims | `page(IdentityClaimResponse)` |
| GET /clans/{clan_id}/claims | `page(IdentityClaimResponse)` |
| POST /clans/{clan_id}/claims/members/{user_id}/prelink [201] | `created(IdentityClaimResponse)` |
| POST /clans/{clan_id}/claims/{claim_id}/approve | `ok(IdentityClaimResponse)` |
| POST /clans/{clan_id}/claims/{claim_id}/reject | `ok(IdentityClaimResponse)` |

### Misc (2)
| Route | Helper | Reused schema | Construction |
|---|---|---|---|
| POST /me/clans/{clan_id}/select | `ok(ClanSwitchResponse)` | `ClanSwitchResponse` | hand-built dict — **guard** |
| GET /events/upcoming | `ok_list(UpcomingEvent)` | `UpcomingEvent` | hand-built dict + `include=person` — **guard** |

## Coherence guards (drift protection — same policy as #80, scaled)

The guard policy: bind a schema to a real handler body **only where the body is a
hand-built dict that parallels the schema** (a genuine second source of truth).
Routes that already `model_dump` *through* the schema are coherent by
construction, and message-only `MessageData` routes have no structure to drift —
neither needs a guard. Under that policy, PR-1 needs exactly **two** guards:

1. **`GET /events/upcoming` → `UpcomingEvent`.** The route hand-assembles the item
   dicts (and the optional `person` sub-object). Validate a real upcoming-events
   body (with `include=person`) against `UpcomingEvent`.
2. **`POST /me/clans/{clan_id}/select` → `ClanSwitchResponse`.** The handler
   returns a hand-built dict. Validate the real body against `ClanSwitchResponse`.

Each guard is added to an existing real-DB test for that route where one exists
(the plan locates them), and sabotage-checked (break a field → guard fails).

## Testing

- Extend `tests/unit/api/test_openapi_typed_responses.py` with representative
  `$ref` assertions: one auth (`onboard` or a `MessageData` route), one persons
  sub-resource (`ok_list`), one claims (`page`), `/me/clans/select`,
  `/events/upcoming`.
- Two coherence guards as above (`@pytest.mark.integration`).
- Existing route/body tests must pass unchanged — the negative control proving
  zero behavior change.

## Definition of done

- All 21 routes carry a typed `responses=` envelope; the generated OpenAPI shows
  named schemas (not bare objects) for each.
- Full gate green: `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.
- The OpenAPI untyped-2xx count drops by 21 (from 32 non-exempt to 11 remaining:
  the 10 PR-2 routes + `/exports/clan`; `/health` is separately exempt, not in
  the 32).
- No app-source body changes; only decorator `responses=`, and additive tests.

## Out of scope (PR-2, separate spec)

`/auth/refresh` (new `TokenPair`), `/persons/search` (new search schema),
`/persons/batch` (new `meta.errors` schema), `/clans/me/users` + `/pending` +
4 action routes (new user-role summary + `{message, user_id}` schemas),
`/me/clans` (non-canonical `meta:{count}`). These carry the design decisions
(non-canonical shapes, key-omission inconsistencies) that warrant their own pass.
