# Typed OpenAPI responses — clean-reuse routes (PR-1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the 21 auxiliary v1 routes that reuse an existing response DTO a typed OpenAPI success envelope (documentation-only `responses=`), so client codegen stops emitting `Record<string, unknown>` for them.

**Architecture:** Same settled pattern as #80 — each route declares its envelope via the route's documentation-only `responses=` argument (`ok`/`page`/`ok_list`/`ok_message`/`created` from `app/schemas/envelope.py`), never `response_model=` (several routes support sparse `fields=`/`include=` subsets). Route/handler bodies unchanged. Two coherence guards for the only two hand-built-dict routes.

**Tech Stack:** FastAPI, Pydantic v2, pytest. Python 3.14+, `uv`-managed. All commands from `backend/`.

## Global Constraints

- Documentation-only `responses=` on every route — **never** `response_model=`.
- **No new schemas** in PR-1 — every route reuses an existing DTO. No route/handler **body** changes — only decorator `responses=` and import lines. App-source behavior unchanged; existing route/body tests pass untouched (negative control).
- Reuse the exact existing schema per the spec table — do not invent fields or rename.
- **Coherence guard** only for the two hand-built-dict routes (`/events/upcoming`, `/me/clans/select`); everything else is coherent-by-construction (dumps through its DTO) or trivial `MessageData` and gets NO guard. Guards are `@pytest.mark.integration` (real Postgres) — executor needs `docker compose up -d pgdb` running.
- Line length 100 (ruff). Use `uv run pytest`/`uv run mypy`; `uvx ruff`. `uvx mypy` is invalid here.
- Branch `feat/typed-responses-clean-reuse` is already checked out.

---

## File Structure

- **Modify** `backend/app/api/v1/auth.py` — envelope + `RegisterResponse` imports; `responses=` on 8 routes.
- **Modify** `backend/app/api/v1/persons.py` — envelope `ok_list` + 6 DTO imports; `responses=` on 6 sub-resource routes.
- **Modify** `backend/app/api/v1/claims.py` — envelope + `IdentityClaimResponse` imports; `responses=` on 5 routes.
- **Modify** `backend/app/api/v1/me.py` — envelope + `ClanSwitchResponse` imports; `responses=` on `/me/clans/select`.
- **Modify** `backend/app/api/v1/events.py` — envelope `ok_list` + `UpcomingEvent` import; `responses=` on `/events/upcoming`.
- **Modify** `backend/tests/unit/api/test_openapi_typed_responses.py` — add `$ref` assertions.
- **Modify** `backend/tests/integration/test_me_and_platform_admin.py` — `/me/clans/select` coherence guard.
- **Modify** `backend/tests/integration/test_upcoming_lunar.py` — `/events/upcoming` coherence guard.

---

### Task 1: Auth router (8 routes)

**Files:**
- Modify: `backend/app/api/v1/auth.py`
- Test: `backend/tests/unit/api/test_openapi_typed_responses.py`

**Interfaces:**
- Consumes: `created`, `ok_message`, `MessageData` from `app.schemas.envelope`; `RegisterResponse` from `app.schemas.auth`.

- [ ] **Step 1: Write the failing OpenAPI tests**

Append to `backend/tests/unit/api/test_openapi_typed_responses.py`:

```python
def test_auth_onboard_is_created_envelope_of_register_response(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/auth/onboard", "post", "201")
    assert "Envelope" in ref and "RegisterResponse" in ref, ref


def test_auth_logout_is_envelope_of_message(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/auth/logout", "post", "200")
    assert "Envelope" in ref and "MessageData" in ref, ref
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k "auth_onboard or auth_logout" -v`
Expected: FAIL — bare-object 200/201 has no `$ref`, so `_response_schema` raises `KeyError`.

- [ ] **Step 3: Add imports**

In `backend/app/api/v1/auth.py`, change the envelope import (currently `from app.schemas.envelope import ok`) to:

```python
from app.schemas.envelope import MessageData, created, ok, ok_message
```

And add `RegisterResponse` to the existing `from app.schemas.auth import (...)` block (line ~24) if not already present.

- [ ] **Step 4: Wire the 8 routes**

Add `responses=` to each decorator (bodies untouched). Match by path:

```python
@router.post("/onboard", status_code=201, responses=created(RegisterResponse))
```
```python
@router.post("/register", status_code=201, responses=created(MessageData))
```
```python
@router.post("/logout", responses=ok_message())
```
```python
@router.post("/forgot-password", responses=ok_message())
```
```python
@router.post("/resend-verification", responses=ok_message())
```
```python
@router.patch("/me", responses=ok_message())
```
```python
@router.post("/me/fcm-token", responses=ok_message())
```
```python
@router.delete("/me/fcm-token", responses=ok_message())
```

Preserve each decorator's existing `status_code=`/`dependencies=`/other kwargs — only ADD `responses=`.

- [ ] **Step 5: Run the auth OpenAPI tests to verify pass**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k "auth_onboard or auth_logout" -v`
Expected: PASS.

- [ ] **Step 6: Format/lint/type gate on touched files**

Run: `cd backend && uvx ruff format app/api/v1/auth.py && uvx ruff check app/api/v1/auth.py && uv run mypy app/api/v1/auth.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add backend/app/api/v1/auth.py backend/tests/unit/api/test_openapi_typed_responses.py
git commit -m "feat(api): typed OpenAPI responses for auth router (clean-reuse)

Documentation-only responses= on 8 auth routes reusing RegisterResponse /
MessageData; no response_model, zero behavior change.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 2: Persons sub-resource routes (6 routes)

**Files:**
- Modify: `backend/app/api/v1/persons.py`
- Test: `backend/tests/unit/api/test_openapi_typed_responses.py`

**Interfaces:**
- Consumes: `ok_list` from `app.schemas.envelope`; `DocumentSummary`, `EventResponse`, `MarriageResponse`, `ParentChildResponse`, `TimelineEvent`, `IdentityClaimResponse` from their schema modules.

- [ ] **Step 1: Write the failing OpenAPI tests**

Append:

```python
def test_persons_marriages_is_envelope_list_of_marriage(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/persons/{person_id}/marriages", "get", "200")
    assert "Envelope" in ref and "MarriageResponse" in ref, ref


def test_persons_timeline_is_envelope_list_of_timeline_event(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/persons/{person_id}/timeline", "get", "200")
    assert "Envelope" in ref and "TimelineEvent" in ref, ref
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k "persons_marriages or persons_timeline" -v`
Expected: FAIL (KeyError — bare object).

- [ ] **Step 3: Add imports**

In `backend/app/api/v1/persons.py`, add `ok_list` to the envelope import (currently `from app.schemas.envelope import created, ok, ok_message, page`):

```python
from app.schemas.envelope import created, ok, ok_list, ok_message, page
```

Add these DTO imports (persons.py imports none of them yet):

```python
from app.schemas.claim import IdentityClaimResponse
from app.schemas.document import DocumentSummary
from app.schemas.event import EventResponse, TimelineEvent
from app.schemas.marriage import MarriageResponse
from app.schemas.parent_child import ParentChildResponse
```

Note `app/schemas/claim.py` — verify the exact class name is `IdentityClaimResponse`; if the submit-claim route returns a differently named response schema, import that instead and use it in Step 4.

- [ ] **Step 4: Wire the 6 routes**

```python
@router.get("/{person_id}/documents", responses=ok_list(DocumentSummary))
```
```python
@router.get("/{person_id}/events", responses=ok_list(EventResponse))
```
```python
@router.get("/{person_id}/marriages", responses=ok_list(MarriageResponse))
```
```python
@router.get("/{person_id}/parent-child", responses=ok_list(ParentChildResponse))
```
```python
@router.get("/{person_id}/timeline", responses=ok_list(TimelineEvent))
```

And the submit-claim route (201):

```python
@router.post("/{person_id}/claim", status_code=201, responses=created(IdentityClaimResponse))
```

Preserve existing decorator kwargs; only ADD `responses=`.

- [ ] **Step 5: Run to verify pass**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k "persons_marriages or persons_timeline" -v`
Expected: PASS.

- [ ] **Step 6: Format/lint/type gate**

Run: `cd backend && uvx ruff format app/api/v1/persons.py && uvx ruff check app/api/v1/persons.py && uv run mypy app/api/v1/persons.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add backend/app/api/v1/persons.py backend/tests/unit/api/test_openapi_typed_responses.py
git commit -m "feat(api): typed OpenAPI responses for persons sub-resources (clean-reuse)

ok_list/created envelopes over existing DTOs (query port already dumps through
them). Doc-only responses=, zero behavior change.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 3: Claims router (5 routes)

**Files:**
- Modify: `backend/app/api/v1/claims.py`
- Test: `backend/tests/unit/api/test_openapi_typed_responses.py`

**Interfaces:**
- Consumes: `created`, `ok`, `page` from `app.schemas.envelope`; `IdentityClaimResponse` from `app.schemas.claim`.

- [ ] **Step 1: Write the failing OpenAPI test**

Append:

```python
def test_claims_list_is_page_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/claims", "get", "200")
    assert "PageEnvelope" in ref and "IdentityClaimResponse" in ref, ref
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k claims_list -v`
Expected: FAIL (KeyError — bare object).

- [ ] **Step 3: Add imports**

In `backend/app/api/v1/claims.py`, add an envelope import and the response schema:

```python
from app.schemas.claim import (
    IdentityClaimPrelink,
    IdentityClaimResponse,
    IdentityClaimReview,
    IdentityClaimUnlink,
)
from app.schemas.envelope import created, ok, page
```

(Merge `IdentityClaimResponse` into the existing `from app.schemas.claim import (...)` line rather than duplicating it. Verify `IdentityClaimResponse` is the class the handlers return via `result.model_dump()`.)

- [ ] **Step 4: Wire the 5 routes**

```python
@router.get("/claims", responses=page(IdentityClaimResponse))
```
Note: the router is mounted so this route's path may be declared as `@router.get("")` or `@router.get("/claims")` depending on the prefix — add `responses=page(IdentityClaimResponse)` to whichever decorator produces `GET /api/v1/claims`.
```python
# GET /clans/{clan_id}/claims
responses=page(IdentityClaimResponse)
```
```python
# POST /clans/{clan_id}/claims/members/{user_id}/prelink  (201)
responses=created(IdentityClaimResponse)
```
```python
# POST /clans/{clan_id}/claims/{claim_id}/approve
responses=ok(IdentityClaimResponse)
```
```python
# POST /clans/{clan_id}/claims/{claim_id}/reject
responses=ok(IdentityClaimResponse)
```

Add `responses=` to each of the 5 decorators, preserving existing kwargs.

- [ ] **Step 5: Run to verify pass**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k claims_list -v`
Expected: PASS.

- [ ] **Step 6: Format/lint/type gate**

Run: `cd backend && uvx ruff format app/api/v1/claims.py && uvx ruff check app/api/v1/claims.py && uv run mypy app/api/v1/claims.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add backend/app/api/v1/claims.py backend/tests/unit/api/test_openapi_typed_responses.py
git commit -m "feat(api): typed OpenAPI responses for claims router (clean-reuse)

page/created/ok envelopes over IdentityClaimResponse (handlers already dump
through it). Doc-only responses=, zero behavior change.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 4: Guarded routes — `/me/clans/select` + `/events/upcoming` (2 routes + 2 coherence guards)

**Files:**
- Modify: `backend/app/api/v1/me.py`, `backend/app/api/v1/events.py`
- Test: `backend/tests/unit/api/test_openapi_typed_responses.py`, `backend/tests/integration/test_me_and_platform_admin.py`, `backend/tests/integration/test_upcoming_lunar.py`

**Interfaces:**
- Consumes: `ok`, `ok_list` from `app.schemas.envelope`; `ClanSwitchResponse` from `app.schemas.clan`; `UpcomingEvent` from `app.schemas.event`.

- [ ] **Step 1: Write the failing OpenAPI tests**

Append:

```python
def test_me_select_is_envelope_of_clan_switch(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/me/clans/{clan_id}/select", "post", "200")
    assert "Envelope" in ref and "ClanSwitchResponse" in ref, ref


def test_events_upcoming_is_envelope_list_of_upcoming_event(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/events/upcoming", "get", "200")
    assert "Envelope" in ref and "UpcomingEvent" in ref, ref
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k "me_select or events_upcoming" -v`
Expected: FAIL (KeyError — bare object).

- [ ] **Step 3: Wire `/me/clans/select`**

In `backend/app/api/v1/me.py`, add imports:

```python
from app.schemas.clan import ClanSwitchResponse
from app.schemas.envelope import ok
```

Wire the route:

```python
@router.post("/clans/{clan_id}/select", responses=ok(ClanSwitchResponse))
```

- [ ] **Step 4: Wire `/events/upcoming`**

In `backend/app/api/v1/events.py`, add `ok_list` to the envelope import (currently `from app.schemas.envelope import created, ok, ok_message, page`):

```python
from app.schemas.envelope import created, ok, ok_list, ok_message, page
```

Add `UpcomingEvent` to the event-schema import (currently `from app.schemas.event import EventCreateRequest, EventResponse, EventUpdateRequest`):

```python
from app.schemas.event import (
    EventCreateRequest,
    EventResponse,
    EventUpdateRequest,
    UpcomingEvent,
)
```

Wire the route:

```python
@router.get("/upcoming", responses=ok_list(UpcomingEvent))
```

- [ ] **Step 5: Run the OpenAPI tests to verify pass**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k "me_select or events_upcoming" -v`
Expected: PASS.

- [ ] **Step 6: Add the `/me/clans/select` coherence guard**

In `backend/tests/integration/test_me_and_platform_admin.py`, in the existing test that calls `select_clan` (the block around `selected = await handler.select_clan(user_id=str(user_id), clan_id=approved_clan)`), add a validation immediately after the existing `assert selected["clan_id"] == str(approved_clan)`:

```python
        # Coherence: the documented response schema must accept the real handler dict.
        from app.schemas.clan import ClanSwitchResponse

        ClanSwitchResponse.model_validate(selected)
```

- [ ] **Step 7: Add the `/events/upcoming` coherence guard**

In `backend/tests/integration/test_upcoming_lunar.py`, add a new test that reuses this file's existing event-seeding + session harness (see `test_upcoming_lunar_uses_converted_date_and_merges_sorted`, which seeds events then calls `get_upcoming`). This guard must validate against the schema the ROUTE emits — so it drives the `EventQueryHandler` (not just the repo) and mirrors the route's `include=person` shaping:

```python
async def test_upcoming_wire_matches_upcoming_event_schema(migrated_db_url):
    """Coherence guard: /events/upcoming hand-builds its item dicts (and the
    optional `person` sub-object), so the documentation-only UpcomingEvent schema
    can drift from the route output. Validate a real body — including the
    person-include shaping the route applies — against UpcomingEvent."""
    from app.application.event.handlers import EventQueryHandler
    from app.infrastructure.persistence.event_query_port import SqlAlchemyEventQueryPort
    from app.schemas.event import UpcomingEvent

    # <reuse this file's seeding: create a clan, a person, and a NORMAL upcoming
    #  solar event within the window; commit. Follow the exact seeding calls used
    #  by test_upcoming_lunar_uses_converted_date_and_merges_sorted in this file.>

    handler = EventQueryHandler(SqlAlchemyEventQueryPort(session))
    today = <the platform-tz today used elsewhere in this file>
    upcoming = await handler.get_upcoming(clan_id=clan_id, days=30, today=today)
    assert upcoming  # non-empty so the loop actually runs

    # Mirror the route's include=person block (app/api/v1/events.py::get_upcoming_events):
    for item in upcoming:
        if item.get("person_id") and item.get("person_name"):
            item["person"] = {
                "id": item["person_id"],
                "full_name": item["person_name"],
                "avatar_url": item.get("person_avatar_url"),
            }
        else:
            item["person"] = None
        UpcomingEvent.model_validate(item)  # raises on drift
```

Fill the seeding + `today`/`session` bindings from the existing tests in the same file (do not invent new helpers). If `EventQueryHandler`/`SqlAlchemyEventQueryPort`/`get_upcoming` signatures differ from the above, match what the existing `test_upcoming_lunar_*` tests and `app/api/v1/events.py` actually use.

- [ ] **Step 8: Run both guards + sabotage-check**

Requires `docker compose up -d pgdb`. Run:
`cd backend && uv run pytest tests/integration/test_me_and_platform_admin.py -k select tests/integration/test_upcoming_lunar.py::test_upcoming_wire_matches_upcoming_event_schema -v`
Expected: PASS. Sabotage-check ONE guard: add a required field to `ClanSwitchResponse` (e.g. `zzz: str`), confirm the select guard FAILS, then revert.

- [ ] **Step 9: Format/lint/type gate**

Run: `cd backend && uvx ruff format app/api/v1/me.py app/api/v1/events.py tests/integration/test_upcoming_lunar.py && uvx ruff check app/api/v1/me.py app/api/v1/events.py tests/integration/test_upcoming_lunar.py && uv run mypy app/api/v1/me.py app/api/v1/events.py`
Expected: no errors.

- [ ] **Step 10: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add backend/app/api/v1/me.py backend/app/api/v1/events.py backend/tests/unit/api/test_openapi_typed_responses.py backend/tests/integration/test_me_and_platform_admin.py backend/tests/integration/test_upcoming_lunar.py
git commit -m "feat(api): typed responses for me/select + events/upcoming (+ coherence guards)

The two PR-1 routes that hand-build a dict paralleling a schema; each bound to a
real handler body by a sabotage-verified coherence guard. Doc-only responses=,
zero behavior change.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 5: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Full quality gate**

Requires `docker compose up -d pgdb`. Run:
```bash
cd "/Volumes/Macext01 HD/playground/familyroots/backend" && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports
```
Expected: all green. No existing test modified except additive OpenAPI assertions + the two coherence guards.

- [ ] **Step 2: OpenAPI untyped-2xx count check**

Run:
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
print('remaining untyped 2xx (non-health):', len(untyped))
for u in sorted(untyped): print('  ', u)
# The 11 PR-2/excluded routes must remain; the 21 PR-1 routes must be gone.
assert len(untyped) == 11, (len(untyped), untyped)
for m, p, c in untyped:
    assert (p.startswith('/api/v1/clans/me/users') or p in {
        '/api/v1/auth/refresh', '/api/v1/persons/search', '/api/v1/persons/batch',
        '/api/v1/me/clans', '/api/v1/exports/clan',
    }), (m, p, c)
print('OK: exactly the 11 PR-2/excluded routes remain untyped')
"
```
Expected: `remaining untyped 2xx (non-health): 11` and `OK: exactly the 11 PR-2/excluded routes remain untyped`.

---

## Self-Review

**Spec coverage:**
- Auth 8 routes → Task 1. ✓
- Persons 6 sub-resources → Task 2. ✓
- Claims 5 routes → Task 3. ✓
- me/select + events/upcoming (2) + their 2 coherence guards → Task 4. ✓
- Full gate + untyped-count assertion (drops 32→11) → Task 5. ✓
- 21 routes total, no new schemas, guard policy (only the 2 hand-built routes) honored. ✓

**Placeholder scan:** The only non-literal region is Task 4 Step 7's seeding block, deliberately delegated to "reuse the same file's existing seeding" with the exact reference test named — this is an instruction to copy existing concrete code, not a vague TODO. Every other step has literal code/commands.

**Type consistency:** Helper names (`ok`/`page`/`ok_list`/`ok_message`/`created`) and schema names (`RegisterResponse`, `MessageData`, `DocumentSummary`, `EventResponse`, `MarriageResponse`, `ParentChildResponse`, `TimelineEvent`, `IdentityClaimResponse`, `ClanSwitchResponse`, `UpcomingEvent`) match the spec table and the verified import locations (`app/schemas/{auth,clan,event,document,marriage,parent_child,claim,envelope}.py`). Tasks 2 & 3 flag the one name to double-check at implementation (`IdentityClaimResponse`).
