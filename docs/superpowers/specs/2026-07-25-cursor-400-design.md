# Malformed Cursor → 400 (M9) — Design

**Date:** 2026-07-25
**Source finding:** M9 in `docs/architecture/backend-review-2026-07-18.md` — a
malformed `?cursor=` 500s on every paginated endpoint; should be a 400
`invalid_cursor`.

## Problem

`decode_cursor` / `decode_fields_cursor` (`app/core/pagination.py`) never wrap
their base64/JSON parsing, and the person-list path further reads specific keys
off the decoded dict:

- `decode_cursor` (used by `paginate_query` → documents, platform-admin clans):
  `base64.urlsafe_b64decode` → `json.loads` → `datetime.fromisoformat` →
  `uuid.UUID`. Garbage input raises `binascii.Error` / `json.JSONDecodeError`
  (a `ValueError`) / `ValueError` / `KeyError`, all unhandled → 500.
- `decode_fields_cursor` (used by `person_repository.list_in_clan`): decodes the
  base64/JSON; then the repo reads `decoded["full_name"]` and
  `uuid.UUID(decoded["id"])` — a well-formed-base64-JSON-but-wrong-shape cursor
  raises `KeyError`/`ValueError` in the repo, *after* the decode → still 500.

So the fix must cover both "not even valid base64/JSON" and "valid JSON, wrong
shape."

## Design

A malformed opaque cursor is a bad request parameter → **400 `invalid_cursor`**
(the review's prescription; consistent with cursors being opaque — the client
must only pass back a value the server issued). Raise `AppError(400,
"invalid_cursor")` at every decode/extract point:

1. **`decode_cursor`** — wrap the whole body (it is self-contained: it knows it
   needs `created_at` + `id`) in `try/except (binascii.Error, ValueError,
   KeyError, TypeError)` → `AppError(400, "invalid_cursor")`.
2. **`decode_fields_cursor`** — wrap the base64/JSON decode (it is generic and
   can't know the expected keys) → same. Still returns the dict on success.
3. **`person_repository.list_in_clan`** — wrap the `decoded["full_name"]` /
   `uuid.UUID(decoded["id"])` extraction (the wrong-shape case that survives #2)
   in the same `try/except` → `AppError(400, "invalid_cursor")`.

`AppError` is already importable in `core/pagination.py` and the repo layer
(`core.exceptions`). No new exception class; one new i18n key.

## Error contract

- **400** `{"error": {"code": "invalid_cursor", "message": <localized>, "detail": {}}}`.
- New i18n key `error.invalid_cursor` in all four locales (the i18n coverage test
  enforces it).
- `docs/contracts/error-codes.md` + `README.md` (pagination section): a
  malformed/tampered cursor yields 400 `invalid_cursor`; the cursor stays opaque.

## What does NOT change

- Valid cursors, pagination behavior, envelope, ordering — all unchanged.
- The cursor scheme (opaque base64) — unchanged.

## Tests (real-DB where the endpoint is exercised; RED-first)

1. **decode_cursor path** (documents or platform-admin list): `GET ...?cursor=%%%garbage%%%`
   → 400 `invalid_cursor` (RED today: 500). Also a valid-base64-but-non-JSON and
   a valid-JSON-missing-keys cursor → 400.
2. **decode_fields_cursor path** (`GET /persons?cursor=garbage`) → 400
   `invalid_cursor` (RED today: 500); plus a valid-base64-JSON-wrong-shape cursor
   (e.g. `{"foo":1}` encoded) → 400 (exercises the repo-extraction guard, #3).
3. **Valid cursor still works** (control): page1 → page2 via the real issued
   cursor → 200 (unchanged).
4. Unit-level: `decode_cursor`/`decode_fields_cursor` raise `AppError(400,
   invalid_cursor)` on representative malformed inputs; a valid round-trip
   decodes correctly.

## Execution

Small, mechanical, no design decision — a lean SDD: Task 1 RED tests, Task 2
fix + docs + i18n, then review + PR.
