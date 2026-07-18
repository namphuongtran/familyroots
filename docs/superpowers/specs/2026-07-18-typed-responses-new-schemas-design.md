# Typed OpenAPI responses — new-schema + non-canonical routes (PR-2 of 2)

**Date:** 2026-07-18
**Status:** Approved (conditioned on the ADR + deprecation markers below) — ready for implementation plan
**Branch:** `feat/typed-responses-new-schemas`

## Problem

After #80 (tree + platform-admin) and #82 (PR-1, clean-reuse), 11 v1 2xx routes
remain untyped in OpenAPI. This PR types the 10 that need **new schemas** or carry
a **non-canonical envelope**; the 11th (`/exports/clan`) is a file download and
stays excluded. After this, only `/exports/clan` (+ the exempt `/health`) is
untyped — `Record<string, unknown>` is eliminated from the client-codegen surface.

## Approach (settled pattern — no deviation)

Documentation-only `responses=` (helpers from `app/schemas/envelope.py`, plus two
bespoke envelope models declared directly via `responses={200: {"model": X}}`),
**never** `response_model=`. New schemas are typed to the JSON **wire** (`str` for
serialized UUIDs, `str | None` for `.isoformat()` datetimes). Route/handler bodies
unchanged. **Zero behavior change** — including the two non-canonical shapes, which
are documented exactly as they are today (owner decision: pure typing, normalize
later; see ADR below).

## New schemas

| Schema | Fields (wire-typed) | File |
|---|---|---|
| `TokenRefreshResponse` | `access_token: str, refresh_token: str, expires_in: int` | `schemas/auth.py` |
| `PersonSearchResult` | `id: str, full_name: str, gender: str, birth_date: HistoricalDate, avatar_url: str \| None, version: int, generation: int \| None, membership_role: str \| None, is_founder: bool` | `schemas/person.py` |
| `BatchError` | `id: str, code: str` | `schemas/person.py` |
| `PersonBatchMeta` | `errors: list[BatchError]` | `schemas/person.py` |
| `PersonBatchEnvelope` | `data: list[PersonResponse]`, `meta: PersonBatchMeta` | `schemas/person.py` |
| `ClanUserSummary` | `id: str, user_id: str, role: str, person_id: str \| None, created_at: str` | `schemas/clan_membership.py` |
| `PendingClanUser` | `id: str, user_id: str, role: str, created_at: str` *(no `person_id` — legacy)* | `schemas/clan_membership.py` |
| `UserActionResponse` | `message: str, user_id: str` | `schemas/clan_membership.py` |
| `UserRoleChangeResponse` | `message: str, user_id: str, role: str` | `schemas/clan_membership.py` |
| `CountMeta` | `count: int` | `schemas/clan.py` |
| `UserClansEnvelope` | `data: list[UserClanMembership]`, `meta: CountMeta` *(non-canonical — legacy)* | `schemas/clan.py` |

`PersonSearchResult.birth_date` reuses the shared `HistoricalDate` schema (the
route builds it via `to_historical_date(...).model_dump()`). `PersonBatchEnvelope`
reuses `PersonResponse` for `data` (batch items are the same dynamic person
projection as `GET /persons/{id}`; sparse `fields=`/`include=` are subsets).
`UserClansEnvelope` reuses `UserClanMembership`.

## Route → helper mapping (10 routes)

| Route | Declaration |
|---|---|
| POST /auth/refresh | `ok(TokenRefreshResponse)` |
| GET /persons/search | `ok_list(PersonSearchResult)` (plain `{data:[...]}`, no meta) |
| POST /persons/batch | `responses={200: {"model": PersonBatchEnvelope}}` (non-canonical `meta.errors`) |
| GET /clans/me/users | `page(ClanUserSummary)` (real cursor meta) |
| GET /clans/me/users/pending | `page(PendingClanUser)` (real cursor meta) |
| POST /clans/me/users/{user_id}/approve | `ok(UserActionResponse)` |
| POST /clans/me/users/{user_id}/reject | `ok(UserActionResponse)` |
| DELETE /clans/me/users/{user_id} | `ok(UserActionResponse)` |
| PATCH /clans/me/users/{user_id}/role | `ok(UserRoleChangeResponse)` |
| GET /me/clans | `responses={200: {"model": UserClansEnvelope}}` (non-canonical `meta.count`) |

## Coherence guards (drift protection — scaled policy)

Every route here hand-builds its dict, so each new schema is a second source of
truth. Guard the **5 with real record structure** via real-DB tests, each
sabotage-verified (break a field → guard fails):

1. `/persons/search` → `PersonSearchResult`
2. `/persons/batch` → `PersonBatchEnvelope` (seed with a **missing id** so `meta.errors` is non-empty and actually validated)
3. `/clans/me/users` → `ClanUserSummary`
4. `/clans/me/users/pending` → `PendingClanUser`
5. `/me/clans` → `UserClansEnvelope`

**Skip guards (documented rationale):**
- `/auth/refresh` → `TokenRefreshResponse`: 3 trivial scalar fields dumped straight
  from the identity provider's token object; a guard would need an identity-provider
  stub for near-zero structural risk. Not worth the harness.
- The `{message, user_id}` action responses (`UserActionResponse`/`UserRoleChangeResponse`):
  1–2 message fields, near-zero drift.

## Long-term / architecture — the non-canonical decision (ADR-024)

Two routes carry envelopes that violate the canonical contract and are **typed
as-is** here (owner decision: pure typing, zero behavior change):
- `GET /me/clans` — `meta:{count}` instead of the canonical `{cursor, has_more, limit}`.
- `GET /clans/me/users/pending` — omits the `person_id` key that its sibling
  `/clans/me/users` includes.

Typing these publishes them as a typed contract, so a later normalization becomes
a breaking change **to a bound contract**. To keep this long-term-sound rather than
silently entrenching debt, PR-2 adds:

1. **ADR-024** (`docs/decisions/024-non-canonical-envelope-exceptions.md`): records
   these two known exceptions, why they are typed as-is now (pure-typing sweep,
   separate from contract normalization), and the commitment to **normalize them
   before the frontend binds** (`/me/clans` → cursor meta; `/pending` → include
   `person_id`) — the deferred L10 envelope-normalization work. Add it to the ADR
   index README in the same PR.
2. **Deprecation markers in code**: `UserClansEnvelope`/`CountMeta` and
   `PendingClanUser` get docstrings marking them a *documented legacy exception,
   not a pattern to copy — pending normalization (ADR-024)*.
3. **`docs/contracts/README.md`**: note these two as known non-canonical exceptions
   pending normalization, and update the "still untyped" caveat to name only
   `/exports/clan` as remaining.

`/persons/batch`'s `meta.errors` is **not** in this bucket — `meta` adjuncts
(`meta.errors`, `meta.warning`) are explicitly sanctioned by CLAUDE.md, so batch is
canonical-compliant; `PersonBatchEnvelope` is a normal typed shape.

## Performance

Documentation-only — zero per-request cost, no `response_model=` re-validation. The
routes' own performance is untouched (`/persons/batch` is already constant-query;
`/persons/search` uses the trigram index). Guards run only in CI.

## Testing

- Extend `tests/unit/api/test_openapi_typed_responses.py` with `$ref` assertions:
  `/auth/refresh`, `/persons/search`, `/persons/batch`, `/clans/me/users`,
  `/clans/me/users/pending`, one action route, `/me/clans`.
- The 5 coherence guards (`@pytest.mark.integration`).
- Existing route/body tests pass unchanged (negative control).

## Definition of done

- All 10 routes carry a typed `responses=` declaration; OpenAPI shows named schemas.
- Full gate green (`pytest -q && ruff check . && ruff format --check . && mypy app/ tests/ && lint-imports`).
- OpenAPI untyped-2xx (non-`/health`) drops 11 → 1 (only `/exports/clan` remains).
- ADR-024 added + indexed; deprecation markers in place; `docs/contracts/README.md` updated.
- No app-source body changes; only decorator `responses=`, new schemas, additive tests, and the docs/ADR.

## Out of scope (explicit)

- `/exports/clan` — file download, envelope-exempt (stays untyped; document as a
  binary response only if trivial, else leave).
- The actual normalization of the two non-canonical shapes — tracked by ADR-024 for
  a deliberate pre-frontend pass, NOT done here.
