# ADR-080: Verify Supabase JWTs With PyJWT, Not python-jose

## Status

Accepted (2026-11-21), resolving issue #363, with the code it records. No migration, no contract change.

## Context

`backend/app/core/security.py` verified every Supabase JWT with `python-jose`. Dependabot reports a
critical algorithm-confusion advisory against it (`<= 3.5.0`) with **no patched version**, so a
bump cannot fix it. The practical risk was limited, because the decode call only accepted the
algorithms in the project's JWKS (falling back to `ES256` and `RS256`), never an HMAC algorithm.
An unmaintained verifier with an unfixable critical advisory should still not stay in the auth path.

## Decision

Verify with PyJWT (`pyjwt[crypto]>=2.14.0`). The behaviour is unchanged: audience `authenticated`,
issuer `<SUPABASE_URL>/auth/v1`, the algorithm allow-list derived from the JWKS (fallback `ES256`,
`RS256`), the existing one-hour asyncio-locked JWKS cache, and `AuthenticationError("invalid_token")`
for every verification failure.

- The JWKS is still fetched by our own async cache. `PyJWKClient` is not used because it fetches
  synchronously with urllib, which would block the event loop and bypass the bounded timeout.
- The signing key is chosen from the cached JWKS by the token's `kid` (a lone key when the token has
  no `kid`). An unknown `kid`, or no `kid` with several keys, is `invalid_token`.
- `python-jose`, `types-python-jose` and their mypy and import-linter entries are removed. `jwt`
  takes `jose`'s place in the import-linter list that keeps it out of the domain layer.

## Consequences

- PyJWT also refuses an HMAC algorithm with an asymmetric JWKS key, so the allow-list is no longer
  the only barrier. `test_hs256_token_signed_with_the_public_key_is_refused` pins the outcome, but
  it **cannot be made to fail by adding `HS256` to the allow-list alone** (measured 2026-11-21: it
  stays green, because PyJWT's key-type check still refuses). It guards the outcome, not the setting.
- No change to which tokens are accepted.
