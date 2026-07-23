# E2E HTTP Journey Harness (B1) — Design

**Date:** 2026-07-18
**Source:** test-posture gap #2 in `docs/architecture/backend-review-2026-07-18.md`
("no full HTTP journey; tree routes have an untested DI/serialization seam — the
exact bug class this repo shipped twice"). Test-infrastructure PR: **no
application code changes**.
**Owner decision:** the H3 defect (tree 404 for API-managed clans) is **pinned
loudly** as a KNOWN_DEFECT test, not xfail'd.

## Problem

`tests/integration/test_auth_http_flow.py` ends at create-person. Beyond that
point, no test drives the app over HTTP with real dependencies:

- `GET /tree`, `/tree/focus/{id}`, `/tree/ancestors/{id}` are only ever hit with
  the handler dependency-overridden (unit) or by calling handlers directly
  (integration) — the DI wiring + read-model serialization seam is unguarded.
- No multi-user flow exists (invite → accept → pending → approve → member acts).
- Role enforcement is never proven over HTTP two-sided.
- Review finding **H3** (thủy tổ unsettable via API → `GET /tree` 404s
  `clan_founder_not_found`, all đời null) has no executable documentation.

## Design

One new module: `backend/tests/integration/test_e2e_journeys.py`, reusing the
proven RS256 pattern (test keypair → JWKS-cache injection → `verify_supabase_token`
runs for real; identity provider is the ONLY stubbed seam, via
`dependency_overrides[get_identity_provider]`; `get_db` overridden to the
migrated-DB session maker; no lifespan). Module-scoped app instance.

### Journey 1 — founder lifecycle (one test, staged asserts)

`register` (`clan_action="create"`) → `login` → `GET /auth/me` → `GET /me/clans`
(canonical plain array per ADR-024) → `POST /me/clans/{id}/select` →
`POST /persons` ×3 (ông, bà, con — with `X-Current-Clan-Id`) →
`POST /relationships/marriages` (ông+bà) →
`POST /relationships/parent-child` ×2 (ông→con biological, bà→con biological) →
`GET /persons` list (cursor envelope shape) →
`GET /tree/focus/{con}` and `GET /tree/ancestors/{con}` →
`GET /exports/clan?format=json` (envelope-exempt attachment; parse the archive,
assert the 3 persons + 2 edges + marriage are present).

Every 2xx hop asserts the canonical envelope (`{"data": ...}`, lists add `meta`);
every date field asserted to be a HistoricalDate object where the contract says so.

**Tree expectations under H3 (current truth, asserted as such):**
- `GET /tree` (no root) → **404 `clan_founder_not_found`** — this is the pinned
  defect (see Journey 3).
- `/tree/focus/{person}` and `/tree/ancestors/{person}` take an explicit person
  and are expected to work — whatever they return today for an API-managed clan
  (including `generation: null` on every node, since no founder anchors đời) is
  asserted explicitly. If the implementer finds these ALSO fail, that is a new
  finding to report, not to paper over.

### Journey 2 — multi-user collaboration (one test, both membership paths)

Admin registers (`clan_action="create"`) → both real joining flows are driven:

- **Invitation path (member A, immediate approval):** admin
  `POST /clans/{clan_id}/invitations` (role=viewer, `X-Current-Clan-Id` =
  path clan per the contract's `clan_context_mismatch` guard) → capture the
  token → member A is an OAuth-style account (JWT minted by the stub for the
  invited email — no register call; the accept handler provisions the profile
  itself via `repo.ensure_profile`) → `POST /invitations/{token}/accept` → 200
  with `{clan_id, role}` — invited accepts are **approved immediately** with
  the invited role.
- **Self-request path (member B, pending → approve):** member B registers with
  `clan_action="join"` + `clan_id` → appears in `GET /clans/me/users/pending`
  (page envelope, `person_id` key present per ADR-024) →
  `POST /clans/me/users/{user_id}/approve` → member B appears approved in
  `GET /clans/me/users`.

Then **two-sided RBAC over HTTP**: viewer member A `GET /persons` → 200 but
`POST /persons` → 403 `insufficient_permissions`; the admin can write. Member A
reads `/tree/focus/{person}` (viewer read access works). Cross-clan isolation:
member A requests Journey-1-style foreign clan data with a foreign
`X-Current-Clan-Id` → 403 `clan_membership_required`.

### Journey 3 — pinned defects + cross-cutting behavior (small focused tests)

- `test_tree_unreachable_for_api_managed_clan_KNOWN_DEFECT_H3`: full API-managed
  clan (from Journey-1-style setup) → `GET /tree` → asserts **404
  `clan_founder_not_found`**. Docstring: pins review finding H3 (no API path can
  set `is_founder`; `PersonCreateRequest` has no such field; no membership PATCH
  exists) and states that PR A3 MUST flip this test to the desired behavior —
  the assertion failing is A3's RED signal.
- `test_malformed_cursor_current_behavior_KNOWN_DEFECT_M9`: `GET /persons?cursor=garbage`
  over HTTP → asserts today's **500** envelope. Docstring pins review finding M9
  (should be 400 `invalid_cursor`); the M9 fix PR flips it.
- `test_error_localization_over_http`: same error requested with
  `Accept-Language: en` → English message; unsupported locale → falls back to vi
  (drives the real LanguageMiddleware; closes the i18n HTTP gap).

## Rate-limit budget (hard constraint)

`RateLimitMiddleware` allows 20 req/min/IP on `/api/v1/auth` + `/api/v1/invitations`
per app instance. Journey 1 spends ~4 on those prefixes; Journey 2 ~6; Journey 3
~2. Total ≤ 12 for the module — acceptable, but the module docstring must carry
the running budget note (house pattern from `test_auth_http_flow.py`), and any
future addition re-counts.

## What this PR is NOT

- No application code changes at all (pure test infrastructure). If a journey
  surfaces a NEW defect beyond H3/M9, the implementer pins current behavior with
  a KNOWN_DEFECT/docstring pointer and reports it — fixes land in their own PRs.
- No BDD layer (separate decision), no perf tests (B3), no failure injection (B2).
- `tests/integration/test_auth_http_flow.py` is left untouched — it remains the
  auth-focused smoke; the new module owns everything past create-person.

## Tests-verify-themselves notes

- Journey tests are ordered stages of one story per test function (sequenced
  asserts with clear stage comments), not dozens of micro-tests — a failure
  message names the failing stage.
- All ids/slugs/emails per-test UUIDs (shared-DB discipline).
- Two-sided isolation where journeys create clans: Journey 2's member must NOT
  see Journey 1's clan data (one explicit cross-clan 403 assert using the other
  journey's clan id — cheap and closes the e2e isolation gap).
