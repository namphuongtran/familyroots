# Typed OpenAPI responses — new-schema + non-canonical routes (PR-2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Type the 10 remaining v1 routes that need new schemas or carry a non-canonical envelope, so only `/exports/clan` (a file download) stays untyped — eliminating `Record<string, unknown>` from client codegen.

**Architecture:** Documentation-only `responses=` (helpers from `app/schemas/envelope.py`, plus two bespoke envelope models passed directly via `responses={200: {"model": X}}`), never `response_model=`. New schemas typed to the JSON wire (`str` for UUIDs, `str | None` for datetimes). Route/handler bodies unchanged — **zero behavior change**, including the two non-canonical shapes (typed as-is; normalization tracked by ADR-024). Five coherence guards for the structured hand-built routes.

**Tech Stack:** FastAPI, Pydantic v2, pytest. Python 3.14+, `uv`-managed. Commands from `backend/`.

## Global Constraints

- Documentation-only `responses=` — **never** `response_model=`.
- New schemas typed to the wire (`str`/`str | None`/`int`), not `uuid.UUID`/`datetime`.
- No route/handler **body** changes — only decorator `responses=`, imports, new schema classes, tests, and the ADR/docs. Existing route/body tests pass untouched (negative control).
- The two non-canonical shapes (`/me/clans` `meta:{count}`, `/clans/me/users/pending` missing `person_id`) are typed **exactly as they are today** — do NOT normalize them here. Mark them deprecated in docstrings and record ADR-024.
- Coherence guard = validate a REAL handler body against the schema, non-vacuous (assert non-empty before looping) and load-bearing (raises on drift), sabotage-verified. `@pytest.mark.integration` → executor needs `docker compose up -d pgdb`.
- Line length 100. `uv run pytest`/`uv run mypy`; `uvx ruff`. `uvx mypy` invalid.
- Branch `feat/typed-responses-new-schemas` already checked out. **Implementer scope discipline:** modify ONLY the files each task names; do NOT touch `.gitignore`, `git push`, open PRs, or edit files outside the task.

## File Structure

- **Modify** `backend/app/schemas/auth.py` — add `TokenRefreshResponse`.
- **Modify** `backend/app/schemas/person.py` — add `PersonSearchResult`, `BatchError`, `PersonBatchMeta`, `PersonBatchEnvelope`.
- **Modify** `backend/app/schemas/clan_membership.py` — add `ClanUserSummary`, `PendingClanUser`, `UserActionResponse`, `UserRoleChangeResponse`.
- **Modify** `backend/app/schemas/clan.py` — add `CountMeta`, `UserClansEnvelope`.
- **Modify** `backend/app/api/v1/{auth,persons,clans,me}.py` — imports + `responses=`.
- **Modify** `backend/tests/unit/api/test_openapi_typed_responses.py` — `$ref` assertions.
- **Modify** integration tests for the 5 guards.
- **Create** `docs/decisions/024-non-canonical-envelope-exceptions.md`; **modify** `docs/decisions/README.md`, `docs/contracts/README.md`.

---

### Task 1: `/auth/refresh` + `TokenRefreshResponse`

**Files:** Modify `backend/app/schemas/auth.py`, `backend/app/api/v1/auth.py`, `backend/tests/unit/api/test_openapi_typed_responses.py`

- [ ] **Step 1: Failing OpenAPI test** — append:

```python
def test_auth_refresh_is_envelope_of_token_refresh(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/auth/refresh", "post", "200")
    assert "Envelope" in ref and "TokenRefreshResponse" in ref, ref
```

- [ ] **Step 2: Verify fail** — `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k auth_refresh -v` → FAIL (KeyError).

- [ ] **Step 3: Add schema** to `backend/app/schemas/auth.py`:

```python
class TokenRefreshResponse(BaseModel):
    """POST /auth/refresh — a refreshed token pair (no user profile)."""

    access_token: str
    refresh_token: str
    expires_in: int
```

- [ ] **Step 4: Wire route** — in `auth.py` add `TokenRefreshResponse` to the existing `from app.schemas.auth import (...)` block; `ok` is already imported. Change the decorator:

```python
@router.post("/refresh", responses=ok(TokenRefreshResponse))
```

- [ ] **Step 5: Verify pass** — same `-k auth_refresh` → PASS.
- [ ] **Step 6: Gate** — `cd backend && uvx ruff format app/schemas/auth.py app/api/v1/auth.py && uvx ruff check app/schemas/auth.py app/api/v1/auth.py && uv run mypy app/schemas/auth.py app/api/v1/auth.py` → clean.
- [ ] **Step 7: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add backend/app/schemas/auth.py backend/app/api/v1/auth.py backend/tests/unit/api/test_openapi_typed_responses.py
git commit -m "feat(api): typed OpenAPI response for /auth/refresh

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 2: `/persons/search` + `/persons/batch` (+ 2 guards)

**Files:** Modify `backend/app/schemas/person.py`, `backend/app/api/v1/persons.py`, `backend/tests/unit/api/test_openapi_typed_responses.py`, `backend/tests/integration/test_person_search_contract.py`, `backend/tests/integration/test_persons_batch_query_scaling.py`

- [ ] **Step 1: Failing OpenAPI tests** — append:

```python
def test_persons_search_is_envelope_list_of_search_result(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/persons/search", "get", "200")
    assert "Envelope" in ref and "PersonSearchResult" in ref, ref


def test_persons_batch_is_batch_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/persons/batch", "post", "200")
    assert "PersonBatchEnvelope" in ref, ref
```

- [ ] **Step 2: Verify fail** — `-k "persons_search or persons_batch"` → FAIL.

- [ ] **Step 3: Add schemas** to `backend/app/schemas/person.py` (`HistoricalDate` and `PersonResponse` already live in this module or are importable here — `PersonResponse` is defined at `person.py:152`; `HistoricalDate` is imported from `app.schemas.historical_date`, add the import if absent):

```python
class PersonSearchResult(BaseModel):
    """One row of GET /persons/search (a lean, search-specific person projection)."""

    id: str
    full_name: str
    gender: str
    birth_date: HistoricalDate
    avatar_url: str | None = None
    version: int
    generation: int | None = None
    membership_role: str | None = None
    is_founder: bool


class BatchError(BaseModel):
    """One per-id failure in a batch fetch."""

    id: str
    code: str


class PersonBatchMeta(BaseModel):
    """meta for POST /persons/batch — the sanctioned `errors` adjunct (CLAUDE.md)."""

    errors: list[BatchError] = []


class PersonBatchEnvelope(BaseModel):
    """POST /persons/batch: {data: [<person>], meta: {errors: [...]}}.

    `data` items are the same dynamic person projection as GET /persons/{id}
    (documented as the full PersonResponse; sparse `fields=`/`include=` are subsets).
    """

    data: list[PersonResponse]
    meta: PersonBatchMeta
```

- [ ] **Step 4: Wire routes** — in `persons.py`: `ok_list` is already imported; add `PersonSearchResult` and `PersonBatchEnvelope` to the existing `from app.schemas.person import (...)` block.

```python
@router.get("/search", responses=ok_list(PersonSearchResult))
```
```python
@router.post("/batch", responses={200: {"model": PersonBatchEnvelope}})
```

(For `/batch`, pass the raw `responses=` dict — the bespoke envelope carries a non-canonical `meta`, so the generic `page()`/`ok()` helpers don't apply.)

- [ ] **Step 5: Verify OpenAPI tests pass** — `-k "persons_search or persons_batch"` → PASS.

- [ ] **Step 6: Search coherence guard** — in `backend/tests/integration/test_person_search_contract.py`, add a test that reuses that file's existing clan/person seeding, runs the real `PersonQueryHandler.search` (or hits the route path the file already exercises), and validates each result dict against `PersonSearchResult`:

```python
async def test_search_wire_matches_person_search_result_schema(<fixtures per this file>):
    """Coherence guard: /persons/search hand-builds its rows — validate a real
    search body against PersonSearchResult so schema/handler drift fails CI."""
    from app.schemas.person import PersonSearchResult
    # <seed a clan + a searchable person using this file's existing helpers; commit>
    results = <call the same search path this file already uses, returning the wire dicts>
    assert results  # non-empty
    for row in results:
        PersonSearchResult.model_validate(row)  # raises on drift
```

Match the file's real fixtures/seeding and the exact call that yields the wire dicts (the list under `"data"`). Do not invent helpers.

- [ ] **Step 7: Batch coherence guard** — in `backend/tests/integration/test_persons_batch_query_scaling.py`, add a test that calls the real batch path with a mix of a REAL id and a MISSING id (so `meta.errors` is populated) and validates the whole body against `PersonBatchEnvelope`:

```python
async def test_batch_wire_matches_batch_envelope_schema(<fixtures per this file>):
    """Coherence guard: validate a real /persons/batch body (including a populated
    meta.errors) against PersonBatchEnvelope."""
    from app.schemas.person import PersonBatchEnvelope
    # <seed a clan + one real person; build the batch response body via the same
    #  handler/route path this file exercises, requesting [real_id, missing_id]>
    assert body["meta"]["errors"]  # the missing id populated errors — non-vacuous
    PersonBatchEnvelope.model_validate(body)  # raises on drift
```

If this file only exercises the query handler (not the full route body assembly), assemble the body the same way `POST /persons/batch` does in `app/api/v1/persons.py` (data list + `meta.errors` from missing ids), or drive the route. Match reality. **The batch route returns `{"data": data, "meta": {"errors": errors}}` always (verified `persons.py:306`), so `PersonBatchEnvelope` fits exactly.** IMPORTANT: use the DEFAULT profile (`"full"`) and do NOT pass `fields=` — `data` items are only `PersonResponse`-complete under the full projection; a `summary`/`detail`/`fields=`-filtered item would fail `PersonResponse.model_validate`. (Extra `include=` keys like `stats` are fine — Pydantic ignores unexpected keys.)

- [ ] **Step 8: Run guards + sabotage-check** — requires pgdb. Run the two new tests by node id. Expected PASS. Sabotage-check one: add a required field to `PersonSearchResult`, confirm its guard FAILS, revert.

- [ ] **Step 9: Gate** — ruff format/check + mypy on `app/schemas/person.py app/api/v1/persons.py` → clean.

- [ ] **Step 10: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add backend/app/schemas/person.py backend/app/api/v1/persons.py backend/tests/unit/api/test_openapi_typed_responses.py backend/tests/integration/test_person_search_contract.py backend/tests/integration/test_persons_batch_query_scaling.py
git commit -m "feat(api): typed OpenAPI responses for /persons/search + /persons/batch

New PersonSearchResult + PersonBatchEnvelope (meta.errors adjunct); two
sabotage-verified coherence guards. Doc-only responses=, zero behavior change.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 3: `/clans/me/users*` (6 routes, + 2 guards)

**Files:** Modify `backend/app/schemas/clan_membership.py`, `backend/app/api/v1/clans.py`, `backend/tests/unit/api/test_openapi_typed_responses.py`, and an integration test for the guards.

- [ ] **Step 1: Failing OpenAPI tests** — append:

```python
def test_clan_users_is_page_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/clans/me/users", "get", "200")
    assert "PageEnvelope" in ref and "ClanUserSummary" in ref, ref


def test_clan_users_pending_is_page_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/clans/me/users/pending", "get", "200")
    assert "PageEnvelope" in ref and "PendingClanUser" in ref, ref


def test_clan_user_role_change_is_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/clans/me/users/{user_id}/role", "patch", "200")
    assert "Envelope" in ref and "UserRoleChangeResponse" in ref, ref
```

- [ ] **Step 2: Verify fail** — `-k "clan_users or clan_user_role"` → FAIL.

- [ ] **Step 3: Add schemas** to `backend/app/schemas/clan_membership.py`:

```python
class ClanUserSummary(BaseModel):
    """One approved member in GET /clans/me/users."""

    id: str
    user_id: str
    role: str
    person_id: str | None = None
    created_at: str


class PendingClanUser(BaseModel):
    """One pending member in GET /clans/me/users/pending.

    LEGACY EXCEPTION (ADR-024): this shape omits the `person_id` key that its
    sibling ClanUserSummary carries. Typed as-is (pure-typing sweep); scheduled
    for normalization (add person_id) before the frontend binds. Do not copy.
    """

    id: str
    user_id: str
    role: str
    created_at: str


class UserActionResponse(BaseModel):
    """approve/reject/remove acknowledgement: {message, user_id}."""

    message: str
    user_id: str


class UserRoleChangeResponse(BaseModel):
    """PATCH .../role acknowledgement: {message, user_id, role}."""

    message: str
    user_id: str
    role: str
```

- [ ] **Step 4: Wire the 6 routes** — in `clans.py` add `page` to the envelope import (currently `from app.schemas.envelope import ok`) → `from app.schemas.envelope import ok, page`; import the 4 new schemas from `app.schemas.clan_membership`. Then:

```python
@router.get("/me/users", responses=page(ClanUserSummary))
```
```python
@router.get("/me/users/pending", responses=page(PendingClanUser))
```
```python
@router.post("/me/users/{user_id}/approve", responses=ok(UserActionResponse))
```
```python
@router.post("/me/users/{user_id}/reject", responses=ok(UserActionResponse))
```
```python
@router.delete("/me/users/{user_id}", responses=ok(UserActionResponse))
```
```python
@router.patch("/me/users/{user_id}/role", responses=ok(UserRoleChangeResponse))
```

Preserve existing decorator kwargs; add ONLY `responses=`.

- [ ] **Step 5: Verify OpenAPI tests pass** — `-k "clan_users or clan_user_role"` → PASS.

- [ ] **Step 6: Coherence guards** (users + pending) — add a test to `backend/tests/integration/test_last_admin_race.py` (it already seeds `user_clan_role` rows and uses `ClanQueryHandler.list_users` — reuse its exact seeding pattern; do NOT invent helpers). Seed a clan with one APPROVED membership (with a linked `person_id`) and one PENDING membership, call the real `ClanQueryHandler.list_users(clan_id, approved=True/False, ...)`, apply the same wire mapping the route does (`app/api/v1/clans.py:84-93` for approved — id/user_id/role/person_id/created_at; `:108-115` for pending — id/user_id/role/created_at, NO person_id), and validate:

```python
async def test_clan_users_wire_matches_schemas(<fixtures>):
    """Coherence guard for /clans/me/users + /pending — validate real rows against
    ClanUserSummary / PendingClanUser (the pending shape omits person_id, as-is)."""
    from app.schemas.clan_membership import ClanUserSummary, PendingClanUser
    # <seed clan + one approved membership (with a linked person_id) + one pending; commit>
    approved = <build the /clans/me/users wire rows the route builds>
    pending = <build the /clans/me/users/pending wire rows the route builds>
    assert approved and pending
    for row in approved:
        ClanUserSummary.model_validate(row)
    for row in pending:
        PendingClanUser.model_validate(row)
```

Reuse existing membership-seeding helpers from the integration suite; build the wire rows exactly as `list_clan_users`/`list_pending_users` do in `clans.py`.

- [ ] **Step 7: Run guards + sabotage-check** — requires pgdb. Run by node id → PASS. Sabotage-check: add a required field to `ClanUserSummary`, confirm FAIL, revert.

- [ ] **Step 8: Gate** — ruff/mypy on `app/schemas/clan_membership.py app/api/v1/clans.py` → clean.

- [ ] **Step 9: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add backend/app/schemas/clan_membership.py backend/app/api/v1/clans.py backend/tests/unit/api/test_openapi_typed_responses.py backend/tests/integration/
git commit -m "feat(api): typed OpenAPI responses for /clans/me/users* (6 routes)

New ClanUserSummary/PendingClanUser (pending omits person_id — legacy, ADR-024)
+ UserActionResponse/UserRoleChangeResponse; 2 coherence guards. Zero behavior change.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 4: `/me/clans` + `UserClansEnvelope` (non-canonical `meta.count`, + 1 guard)

**Files:** Modify `backend/app/schemas/clan.py`, `backend/app/api/v1/me.py`, `backend/tests/unit/api/test_openapi_typed_responses.py`, `backend/tests/integration/test_me_and_platform_admin.py`

- [ ] **Step 1: Failing OpenAPI test** — append:

```python
def test_me_clans_is_user_clans_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/me/clans", "get", "200")
    assert "UserClansEnvelope" in ref, ref
```

- [ ] **Step 2: Verify fail** — `-k me_clans_is_user_clans` → FAIL.

- [ ] **Step 3: Add schemas** to `backend/app/schemas/clan.py` (`UserClanMembership` already defined here at `clan.py:9`):

```python
class CountMeta(BaseModel):
    """LEGACY meta for GET /me/clans (ADR-024): a bare {count} instead of the
    canonical {cursor, has_more, limit}. Typed as-is; scheduled for normalization
    to cursor meta before the frontend binds. Do not copy this shape."""

    count: int


class UserClansEnvelope(BaseModel):
    """GET /me/clans: {data: [UserClanMembership], meta: {count}} — non-canonical
    (see CountMeta / ADR-024)."""

    data: list[UserClanMembership]
    meta: CountMeta
```

- [ ] **Step 4: Wire route** — in `me.py` add `UserClansEnvelope` to the existing `from app.schemas.clan import ClanSwitchResponse` → `from app.schemas.clan import ClanSwitchResponse, UserClansEnvelope`:

```python
@router.get("/clans", responses={200: {"model": UserClansEnvelope}})
```

- [ ] **Step 5: Verify pass** — `-k me_clans_is_user_clans` → PASS.

- [ ] **Step 6: Coherence guard** — in `backend/tests/integration/test_me_and_platform_admin.py`, in/near the existing `list_clans` test (`test_me_lists_only_approved_and_blocks_non_member`), build the real `/me/clans` wire body and validate it:

```python
        # Coherence: the documented UserClansEnvelope must accept the real wire body.
        from app.schemas.clan import UserClansEnvelope

        result = await handler.list_clans(user_id=str(user_id))
        body = {"data": result["clans"], "meta": {"count": result["count"]}}
        assert body["data"]  # non-empty
        UserClansEnvelope.model_validate(body)
```

(Place it where `handler` and an approved-membership `user_id` are already in scope.)

- [ ] **Step 7: Run guard + sabotage-check** — requires pgdb. Run the test → PASS. Sabotage-check: add a required field to `CountMeta`, confirm FAIL, revert.

- [ ] **Step 8: Gate** — ruff/mypy on `app/schemas/clan.py app/api/v1/me.py` → clean.

- [ ] **Step 9: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add backend/app/schemas/clan.py backend/app/api/v1/me.py backend/tests/unit/api/test_openapi_typed_responses.py backend/tests/integration/test_me_and_platform_admin.py
git commit -m "feat(api): typed OpenAPI response for /me/clans (non-canonical meta.count)

New UserClansEnvelope/CountMeta, marked legacy (ADR-024); coherence guard.
Zero behavior change.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 5: ADR-024 + docs

**Files:** Create `docs/decisions/024-non-canonical-envelope-exceptions.md`; modify `docs/decisions/README.md`, `docs/contracts/README.md`.

- [ ] **Step 1: Write ADR-024** — create `docs/decisions/024-non-canonical-envelope-exceptions.md`:

```markdown
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
```

- [ ] **Step 2: Index the ADR** — in `docs/decisions/README.md`, add a row after the `023` row:

```
| [024](024-non-canonical-envelope-exceptions.md) | Non-Canonical Envelope Exceptions Typed As-Is (Normalize Pre-Frontend) | Accepted |
```

- [ ] **Step 3: Update the contracts caveat** — in `docs/contracts/README.md`, change the "some routes remain untyped" passage so it names only `/exports/clan`, and note the two known non-canonical exceptions. Replace:

```
  `fields=` is a key-subset of the documented full shape. Some routes whose
  payloads are still dynamic dicts (e.g. `/events/upcoming`, `/auth` token
  bodies, several `/persons/*` sub-resources, `/clans/me/users*`, `/me/clans`,
  `/claims*`, `/exports/clan`) remain untyped in OpenAPI until their read
  models are typed — the per-endpoint contract docs stay authoritative for
  those. This list is illustrative, not exhaustive.
```

with:

```
  `fields=` is a key-subset of the documented full shape. All v1 JSON 2xx
  responses are now typed except `GET /exports/clan` (a file download,
  envelope-exempt). Two typed routes carry a known non-canonical envelope,
  documented as legacy exceptions pending normalization before the frontend
  binds (ADR-024): `GET /me/clans` (`meta:{count}`) and
  `GET /clans/me/users/pending` (omits `person_id`).
```

- [ ] **Step 4: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add docs/decisions/024-non-canonical-envelope-exceptions.md docs/decisions/README.md docs/contracts/README.md
git commit -m "docs(adr): ADR-024 non-canonical envelope exceptions (normalize pre-frontend)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 6: Full-suite verification

**Files:** none.

- [ ] **Step 1: Full gate** — requires pgdb. Run:
```bash
cd "/Volumes/Macext01 HD/playground/familyroots/backend" && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports
```
Expected: all green.

- [ ] **Step 2: OpenAPI untyped-2xx check** — Run:
```bash
cd "/Volumes/Macext01 HD/playground/familyroots/backend" && uv run python -c "
from app.main import create_app
spec = create_app().openapi()
untyped = []
for path, ops in spec['paths'].items():
    if path == '/health':
        continue
    for method, op in ops.items():
        for code, resp in op.get('responses', {}).items():
            if not str(code).startswith('2'):
                continue
            content = resp.get('content', {})
            if not content:
                continue
            schema = content.get('application/json', {}).get('schema', {})
            if '\$ref' not in schema and 'allOf' not in schema and 'items' not in schema:
                untyped.append((method.upper(), path, code))
print('remaining untyped 2xx (non-health):', len(untyped), untyped)
assert len(untyped) == 1 and untyped[0][1] == '/api/v1/exports/clan', untyped
print('OK: only /exports/clan remains untyped')
"
```
Expected: `remaining untyped 2xx (non-health): 1` and `OK: only /exports/clan remains untyped`.

---

## Self-Review

**Spec coverage:**
- `/auth/refresh` + `TokenRefreshResponse` → Task 1. ✓
- `/persons/search`, `/persons/batch` + schemas + 2 guards → Task 2. ✓
- `/clans/me/users*` (6) + 4 schemas + 2 guards → Task 3. ✓
- `/me/clans` + `UserClansEnvelope`/`CountMeta` + 1 guard → Task 4. ✓
- ADR-024 + deprecation markers (in Tasks 3/4 docstrings) + README index + contracts caveat → Task 5 (+ 3/4). ✓
- 5 coherence guards total (search, batch, users, pending, me/clans); refresh + action-messages skipped per policy. ✓
- Full gate + untyped-count → 1 (`/exports/clan`) → Task 6. ✓

**Placeholder scan:** Guard test bodies (Tasks 2/3) delegate seeding to "reuse this file's existing fixtures" with the concrete validation shown — an instruction to copy existing code, not a vague TODO. All schema code, decorator wiring, ADR text, and doc edits are literal.

**Type consistency:** Helper names (`ok`/`page`/`ok_list`) and schema names (`TokenRefreshResponse`, `PersonSearchResult`, `BatchError`, `PersonBatchMeta`, `PersonBatchEnvelope`, `ClanUserSummary`, `PendingClanUser`, `UserActionResponse`, `UserRoleChangeResponse`, `CountMeta`, `UserClansEnvelope`) are identical across schema definitions, route wiring, tests, and the ADR. Reused types (`PersonResponse` person.py:152, `HistoricalDate`, `UserClanMembership` clan.py:9) verified present.
