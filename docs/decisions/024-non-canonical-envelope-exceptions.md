# ADR-024: Non-Canonical Envelope Exceptions Typed As-Is (Normalize Pre-Frontend)

## Status
Accepted (2026-07-18)

## Context
The typed-OpenAPI sweep (#80, #82, this PR) gives every v1 2xx a named response
schema so client codegen stops emitting `Record<string, unknown>`. Two routes
carry envelopes that violate the canonical contract (`docs/contracts/`):

- `GET /me/clans` returns `meta: {count}` instead of the canonical
  `{cursor, has_more, limit}`.
- `GET /clans/me/users/pending` omits the `person_id` key that its sibling
  `GET /clans/me/users` includes.

Both predate the envelope freeze (L10 debt). Normalizing them is a breaking
contract change; the sweep's job is to describe reality, not change contracts.

## Decision
Type both shapes **exactly as they are today** (zero behavior change), with:
- `UserClansEnvelope`/`CountMeta` and `PendingClanUser` marked in-code as legacy
  exceptions, "do not copy".
- This ADR recording the intent to **normalize both before the frontend binds**
  (`/me/clans` → cursor meta; `/pending` → include `person_id`), so the debt is
  scheduled, not entrenched. The frontend has not been built, so no client is
  bound yet — the normalization window is open and must be used before it closes.

`POST /persons/batch`'s `meta.errors` is NOT an exception: `meta` adjuncts
(`meta.errors`, `meta.warning`) are sanctioned by the canonical contract, so
`PersonBatchEnvelope` is a normal typed shape.

## Consequences
- Codegen now has honest types for these routes (better than untyped).
- A future normalization PR will change these two typed schemas — acceptable
  because it happens before any client binds; tracked here so it is not forgotten.
- New endpoints MUST use the canonical envelope; these two remain the only
  sanctioned exceptions until normalized.
