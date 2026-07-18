# Typed OpenAPI responses for tree + platform-admin — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every route in `app/api/v1/tree.py` and `app/api/v1/platform_admin.py` a typed OpenAPI success envelope so client codegen stops emitting `Record<string, unknown>` for them — the last two untyped v1 routers.

**Architecture:** Follow the settled pattern from commit `4b904a6`: each route declares its success shape via the route's documentation-only `responses=` argument using the helpers in `app/schemas/envelope.py` (`ok`, `page`, `ok_list`). Never `response_model=` (runtime re-validation would break sparse `profile=`/`fields=` responses). New Pydantic response schemas are typed to the JSON **wire** (ids/dates are strings, matching the handlers' `str(...)`/`.isoformat()`). Zero runtime/behavior change.

**Tech Stack:** FastAPI, Pydantic v2, pytest. Python 3.14+, `uv`-managed.

## Global Constraints

- Documentation-only `responses=` on every route — **never** `response_model=`. Copied from spec: runtime re-validation would break the sparse `fields=`/`profile=` subset responses.
- New response schemas are typed to the wire: `str` for serialized UUIDs, `str | None` for `.isoformat()` datetimes. Do **not** reuse the domain read-model dataclasses in `app/domain/platform_admin/query_port.py` (they carry `uuid.UUID`/`datetime`, not the wire shape).
- No route/handler **body** changes — only decorator `responses=` and new schema files. App-source behavior is unchanged; the negative control is that existing route/integration **body** assertions pass untouched. Test files may gain additive assertions / new tests (they strengthen coverage, not behavior).
- **Schema↔body coherence guard:** each new/reused response schema must be validated against a *real* handler wire dict in a test, so the documentation-only schema cannot silently drift from what the handler emits. These are `@pytest.mark.integration` (real Postgres) — the executor needs `docker compose up -d pgdb` running.
- Full quality gate before claiming done: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`
- Line length 100 (ruff). All commands run from `backend/`.
- Branch is already created: `feat/typed-responses-tree-platform-admin`.

---

## File Structure

- **Create** `backend/app/schemas/platform_admin.py` — 6 wire-typed Pydantic response models for the platform-admin router.
- **Modify** `backend/app/schemas/tree.py` — append 2 new schemas (`PathStep`, `RelationshipPathResponse`).
- **Modify** `backend/app/api/v1/platform_admin.py` — add `responses=` to all 6 routes (+ imports).
- **Modify** `backend/app/api/v1/tree.py` — add `responses=` to all 5 routes (+ imports).
- **Modify** `backend/tests/unit/api/test_openapi_typed_responses.py` — add 6 assertions; drop the "follow-up" caveat from the module docstring.
- **Modify** `docs/contracts/README.md` — remove tree/platform-admin from the "still untyped" note.

---

### Task 1: Platform-admin typed response schemas + route wiring

**Files:**
- Create: `backend/app/schemas/platform_admin.py`
- Modify: `backend/app/api/v1/platform_admin.py`
- Test: `backend/tests/unit/api/test_openapi_typed_responses.py`

**Interfaces:**
- Consumes: `ok`, `page` from `app.schemas.envelope` (existing helpers: `ok(model)` → `{200: {"model": Envelope[model]}}`, `page(model)` → `{200: {"model": PageEnvelope[model]}}`).
- Produces: response schemas `ClanSummaryResponse`, `ClanStatsResponse`, `ClanDetailResponse`, `ClanStatusResponse`, `PlatformMetricsResponse`, `AuditLogEntryResponse` in `app.schemas.platform_admin`.

- [ ] **Step 1: Write the failing OpenAPI-shape tests**

Append to `backend/tests/unit/api/test_openapi_typed_responses.py`:

```python
def test_platform_clans_is_page_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/platform/clans", "get", "200")
    assert "PageEnvelope" in ref and "ClanSummaryResponse" in ref, ref


def test_platform_clan_detail_is_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/platform/clans/{clan_id}", "get", "200")
    assert "Envelope" in ref and "ClanDetailResponse" in ref, ref


def test_platform_metrics_is_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/platform/metrics", "get", "200")
    assert "Envelope" in ref and "PlatformMetricsResponse" in ref, ref
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k platform -v`
Expected: FAIL — the current 200 response has no `$ref` (bare object), so `_response_schema` raises `KeyError` on `["schema"]["$ref"]`.

- [ ] **Step 3: Create the response schemas**

Create `backend/app/schemas/platform_admin.py`:

```python
"""Pydantic v2 response schemas for platform-admin routes — OpenAPI docs only.

These mirror the exact JSON wire shapes emitted by ``PlatformAdminQueryHandler``
(``app/application/platform_admin/handlers.py``): UUIDs and datetimes are already
serialized to strings there, so these are typed to the wire (``str``), NOT to the
domain read-model dataclasses (which carry ``uuid.UUID``/``datetime``). Declared
via each route's documentation-only ``responses=`` — never ``response_model=``.
"""

from __future__ import annotations

from pydantic import BaseModel


class ClanSummaryResponse(BaseModel):
    """One clan row in the platform-wide clan listing."""

    id: str
    name: str
    slug: str
    is_active: bool
    created_at: str | None = None


class ClanStatsResponse(BaseModel):
    """Aggregate membership counts for a single clan."""

    total_members: int
    total_users: int


class ClanDetailResponse(BaseModel):
    """Detail projection for a single clan, with aggregate stats."""

    id: str
    name: str
    slug: str
    is_active: bool
    description: str | None = None
    origin_place: str | None = None
    stats: ClanStatsResponse
    created_at: str | None = None


class ClanStatusResponse(BaseModel):
    """Acknowledgement body for suspend/reactivate."""

    is_active: bool
    clan_id: str


class PlatformMetricsResponse(BaseModel):
    """Platform-wide adoption metrics."""

    total_clans: int
    active_clans: int
    suspended_clans: int
    total_members: int
    total_users: int


class AuditLogEntryResponse(BaseModel):
    """One entry in the cross-clan audit log."""

    id: str
    clan_id: str | None = None
    actor_id: str
    actor_role: str
    action: str
    resource_type: str
    resource_id: str | None = None
    created_at: str | None = None
```

- [ ] **Step 4: Wire the routes**

In `backend/app/api/v1/platform_admin.py`, add these imports (alongside the existing imports):

```python
from app.schemas.envelope import ok, page
from app.schemas.platform_admin import (
    AuditLogEntryResponse,
    ClanDetailResponse,
    ClanStatusResponse,
    ClanSummaryResponse,
    PlatformMetricsResponse,
)
```

Then add `responses=` to each route decorator (leave every other argument and the function bodies untouched):

```python
@router.get("/clans", dependencies=[Depends(get_super_admin)], responses=page(ClanSummaryResponse))
```
```python
@router.get(
    "/clans/{clan_id}",
    dependencies=[Depends(get_super_admin)],
    responses=ok(ClanDetailResponse),
)
```
```python
@router.post("/clans/{clan_id}/suspend", responses=ok(ClanStatusResponse))
```
```python
@router.post("/clans/{clan_id}/reactivate", responses=ok(ClanStatusResponse))
```
```python
@router.get("/metrics", dependencies=[Depends(get_super_admin)], responses=ok(PlatformMetricsResponse))
```
```python
@router.get("/audit-log", dependencies=[Depends(get_super_admin)], responses=page(AuditLogEntryResponse))
```

- [ ] **Step 5: Run the platform tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k platform -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Add the schema↔body coherence guard**

The `responses=` schemas are documentation-only, so nothing yet ties them to the
handler's actual wire dicts. Bind them by validating the real dicts (already in
scope) against the new schemas. Append to the **existing** test
`test_platform_admin_handler_preserves_wire_contract` in
`backend/tests/integration/test_me_and_platform_admin.py`, at the very end of the
function (the variables `detail`, `clans`, `metrics`, `clan_log`, `platform_log`
are already built earlier in that test):

```python
    # Coherence: the documentation-only OpenAPI response schemas must accept the
    # real handler wire dicts, or a schema/handler drift ships silently to codegen.
    from app.schemas.platform_admin import (
        AuditLogEntryResponse,
        ClanDetailResponse,
        ClanSummaryResponse,
        PlatformMetricsResponse,
    )

    ClanDetailResponse.model_validate(detail)
    for c in clans["data"]:
        ClanSummaryResponse.model_validate(c)
    PlatformMetricsResponse.model_validate(metrics)
    for e in clan_log["data"]:
        AuditLogEntryResponse.model_validate(e)
    for e in platform_log["data"]:
        AuditLogEntryResponse.model_validate(e)  # clan_id is None here — must validate
```

Note: `ClanStatusResponse` (suspend/reactivate) is a 2-field literal built inline in
the route (`{"is_active": ..., "clan_id": str(...)}`) with negligible drift surface;
it is covered by the OpenAPI-shape presence, not a separate body test.

- [ ] **Step 7: Run the platform tests (unit + the coherence guard)**

Requires `docker compose up -d pgdb`. Run:
`cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k platform tests/integration/test_me_and_platform_admin.py::test_platform_admin_handler_preserves_wire_contract -v`
Expected: PASS. Sabotage-check the guard: temporarily rename a field in `ClanDetailResponse` (e.g. `slug` → `slugX`) and confirm the coherence test FAILS, then revert.

- [ ] **Step 8: Run format/lint/type gate on the touched files**

Run: `cd backend && uvx ruff format app/schemas/platform_admin.py app/api/v1/platform_admin.py && uvx ruff check app/schemas/platform_admin.py app/api/v1/platform_admin.py && uv run mypy app/schemas/platform_admin.py app/api/v1/platform_admin.py`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add backend/app/schemas/platform_admin.py backend/app/api/v1/platform_admin.py backend/tests/unit/api/test_openapi_typed_responses.py backend/tests/integration/test_me_and_platform_admin.py
git commit -m "feat(api): typed OpenAPI responses for platform-admin router

Documentation-only responses= envelopes (wire-typed schemas mirroring the
handler's str-serialized shapes); no response_model, zero behavior change.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 2: Tree typed response schemas + route wiring

**Files:**
- Modify: `backend/app/schemas/tree.py`
- Modify: `backend/app/api/v1/tree.py`
- Test: `backend/tests/unit/api/test_openapi_typed_responses.py`

**Interfaces:**
- Consumes: `ok`, `ok_list` from `app.schemas.envelope` (`ok(model)` → `{200: {"model": Envelope[model]}}`, `ok_list(model)` → `{200: {"model": Envelope[list[model]]}}`); existing schemas `FocusView`, `TreeResponse`, `TreeNodeDetail` from `app.schemas.tree`.
- Produces: new schemas `PathStep`, `RelationshipPathResponse` in `app.schemas.tree`.

- [ ] **Step 1: Write the failing OpenAPI-shape tests**

Append to `backend/tests/unit/api/test_openapi_typed_responses.py`:

```python
def test_tree_full_is_envelope_of_tree_response(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/tree", "get", "200")
    assert "Envelope" in ref and "TreeResponse" in ref, ref


def test_tree_ancestors_is_envelope_list_of_detail_node(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/tree/ancestors/{person_id}", "get", "200")
    assert "Envelope" in ref and "TreeNodeDetail" in ref, ref


def test_tree_path_is_envelope_of_relationship_path(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/tree/path", "get", "200")
    assert "Envelope" in ref and "RelationshipPathResponse" in ref, ref
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k tree -v`
Expected: FAIL — the current 200 responses have no `$ref` (bare object), so `_response_schema` raises `KeyError`.

- [ ] **Step 3: Add the new tree schemas**

Append to `backend/app/schemas/tree.py` (after `FocusView`):

```python
class PathStep(BaseModel):
    """One node along a relationship path.

    The kinship-descriptor-only fields (``birth_date``/``birth_date_precision``)
    are stripped by the handler before the response, so they are absent here.
    """

    person_id: str
    full_name: str
    gender: str
    edge_type: str | None = None
    avatar_url: str | None = None


class RelationshipPathResponse(BaseModel):
    """Response body for ``GET /tree/path``."""

    path: list[PathStep] = []
    description: str | None = None
    found: bool = False
```

- [ ] **Step 4: Wire the routes**

In `backend/app/api/v1/tree.py`, replace the existing tree-schema import line

```python
from app.schemas.tree import FocusView, TreeNodeDetail, TreeNodeSummary
```

with

```python
from app.schemas.envelope import ok, ok_list
from app.schemas.tree import (
    FocusView,
    RelationshipPathResponse,
    TreeNodeDetail,
    TreeNodeSummary,
    TreeResponse,
)
```

Then add `responses=` to each route decorator (bodies untouched):

```python
@router.get("", responses=ok(TreeResponse))
```
```python
@router.get("/subtree/{person_id}", responses=ok(TreeResponse))
```
```python
@router.get("/ancestors/{person_id}", responses=ok_list(TreeNodeDetail))
```
```python
@router.get("/focus/{person_id}", responses=ok(FocusView))
```
```python
@router.get("/path", responses=ok(RelationshipPathResponse))
```

- [ ] **Step 5: Run the tree tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k tree -v`
Expected: PASS (3 tests).

If `test_tree_ancestors_is_envelope_list_of_detail_node` fails because the 200 schema is inlined rather than a top-level `$ref` (the `Envelope[list[...]]` component can nest differently), extend the helper: read `op["responses"]["200"]["content"]["application/json"]["schema"]` and accept either a top-level `$ref` or an `allOf`/`items` that references `TreeNodeDetail`. Do this only if the direct `$ref` assertion fails.

- [ ] **Step 6: Add the schema↔body coherence guard**

Bind the tree schemas to real handler output. Append a new test to the **existing**
`backend/tests/integration/test_tree_focus.py` (it already has the `async_session`
fixture and the `_clan` / `_person` / `_member` / `_pc` seeding helpers and imports
`TreeQueryHandler` + `SqlAlchemyTreeRepository`):

```python
async def test_tree_handler_output_matches_response_schemas(
    async_session: AsyncSession,
) -> None:
    """Coherence guard: the handler's wire dicts must validate against the
    documentation-only OpenAPI response schemas, so a schema/handler drift fails CI
    instead of shipping a wrong type to codegen. (Focus is omitted — its route
    already coerces to FocusView at runtime, so coherence is guaranteed there.)"""
    from app.application.tree.queries import FindPath, GetAncestors, GetFullTree
    from app.schemas.tree import RelationshipPathResponse, TreeNodeDetail, TreeResponse

    creator = uuid.uuid4()
    clan_id = await _clan(async_session)
    gp = await _person(async_session, clan_id, creator, "GP")
    dad = await _person(async_session, clan_id, creator, "Dad")
    child = await _person(async_session, clan_id, creator, "Child")
    for person, founder in ((gp, True), (dad, False), (child, False)):
        await _member(async_session, person, clan_id, is_founder=founder)
    await _pc(async_session, gp, dad, clan_id, creator)
    await _pc(async_session, dad, child, clan_id, creator)
    await async_session.commit()

    handler = TreeQueryHandler(SqlAlchemyTreeRepository(async_session))

    full = await handler.get_full_tree(
        GetFullTree(clan_id=clan_id, root_person_id=gp, max_generations=10)
    )
    TreeResponse.model_validate(full)  # raises on drift

    ancestors = await handler.get_ancestors(GetAncestors(person_id=child, clan_id=clan_id))
    assert ancestors  # non-empty so the loop actually exercises the schema
    for node in ancestors:
        TreeNodeDetail.model_validate(node)  # raises on drift

    path = await handler.find_path(FindPath(from_id=child, to_id=gp, clan_id=clan_id))
    assert path["found"] is True
    RelationshipPathResponse.model_validate(path)  # raises on drift
```

Note: Pydantic ignores unexpected keys by default, so this guard catches
missing/mis-typed documented fields (the drift clients feel), not extra
undocumented keys — the intended, sufficient guarantee.

- [ ] **Step 7: Run the tree tests (unit + coherence guard)**

Requires `docker compose up -d pgdb`. Run:
`cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k tree tests/integration/test_tree_focus.py::test_tree_handler_output_matches_response_schemas -v`
Expected: PASS. Sabotage-check: temporarily add a required field to `PathStep` (e.g. `foo: str`) and confirm the coherence test FAILS, then revert.

- [ ] **Step 8: Run format/lint/type gate on the touched files**

Run: `cd backend && uvx ruff format app/schemas/tree.py app/api/v1/tree.py tests/integration/test_tree_focus.py && uvx ruff check app/schemas/tree.py app/api/v1/tree.py tests/integration/test_tree_focus.py && uv run mypy app/schemas/tree.py app/api/v1/tree.py`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add backend/app/schemas/tree.py backend/app/api/v1/tree.py backend/tests/unit/api/test_openapi_typed_responses.py backend/tests/integration/test_tree_focus.py
git commit -m "feat(api): typed OpenAPI responses for tree router

Wire focus/full/subtree/ancestors/path to documentation-only responses=
envelopes; new PathStep/RelationshipPathResponse for /tree/path. Ancestors
documented as the widest profile (TreeNodeDetail). Zero behavior change.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 3: Remove the "still untyped" caveats in docs + test docstring

**Files:**
- Modify: `docs/contracts/README.md`
- Modify: `backend/tests/unit/api/test_openapi_typed_responses.py`

**Interfaces:**
- Consumes: nothing (documentation cleanup).
- Produces: nothing.

- [ ] **Step 1: Update the contracts README note**

In `docs/contracts/README.md`, replace this passage:

```
  fields=` is a key-subset of the documented full shape. Routes whose
  payloads are still dynamic dicts (tree, platform-admin, /events/upcoming,
  /auth token bodies) remain untyped in OpenAPI until their read models are
  typed — the per-endpoint contract docs stay authoritative for those.
```

with:

```
  fields=` is a key-subset of the documented full shape. A few routes whose
  payloads are still dynamic dicts (/events/upcoming, /auth token bodies)
  remain untyped in OpenAPI until their read models are typed — the
  per-endpoint contract docs stay authoritative for those.
```

- [ ] **Step 2: Update the test module docstring**

In `backend/tests/unit/api/test_openapi_typed_responses.py`, replace this sentence in the module docstring:

```
These tests pin representative routes; the sweep covers all routers that
have typed payload models (tree/platform-admin read models are follow-up).
```

with:

```
These tests pin representative routes across every v1 router, including
tree and platform-admin.
```

- [ ] **Step 3: Verify no other reference to the caveat remains**

Run: `cd "/Volumes/Macext01 HD/playground/familyroots" && grep -rn "platform-admin read models are follow-up\|(tree, platform-admin," docs/ backend/`
Expected: no matches.

- [ ] **Step 4: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add docs/contracts/README.md backend/tests/unit/api/test_openapi_typed_responses.py
git commit -m "docs(contracts): drop tree/platform-admin from the untyped-routes note

Both routers now carry typed OpenAPI responses.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 4: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full quality gate**

Run:
```bash
cd "/Volumes/Macext01 HD/playground/familyroots/backend" && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports
```
Expected: all green. Test count should be the prior total + 6 new OpenAPI tests, with **no** existing test modified beyond the docstring/additions (negative control: behavior unchanged).

- [ ] **Step 2: Sanity-check the generated OpenAPI has zero bare-object 2xx on these routers**

Run:
```bash
cd "/Volumes/Macext01 HD/playground/familyroots/backend" && uv run python -c "
from app.main import create_app
spec = create_app().openapi()
bad = []
for path, ops in spec['paths'].items():
    if not (path.startswith('/api/v1/tree') or path.startswith('/api/v1/platform')):
        continue
    for method, op in ops.items():
        for code, resp in op.get('responses', {}).items():
            if str(code).startswith('2'):
                schema = resp.get('content', {}).get('application/json', {}).get('schema', {})
                if '\$ref' not in schema and 'allOf' not in schema and 'items' not in schema:
                    bad.append((method.upper(), path, code))
print('untyped 2xx:', bad)
assert not bad, bad
"
```
Expected: `untyped 2xx: []`.

---

## Self-Review

**Spec coverage:**
- Platform-admin 6 schemas + 6 routes → Task 1. ✓
- Tree focus/full/subtree/ancestors/path wiring → Task 2. ✓
- New `PathStep`/`RelationshipPathResponse` → Task 2 Step 3. ✓
- Ancestors documented as `TreeNodeDetail` (judgment ①) → Task 2 Step 4. ✓
- OpenAPI test additions (6) → Tasks 1 & 2. ✓
- Schema↔body coherence guards (drift protection) → Task 1 Step 6 (platform, 4 shapes) + Task 2 Step 6 (tree: full/ancestors/path), each sabotage-checked. ✓
- Contracts README note + test docstring caveat → Task 3. ✓
- Full gate + zero-behavior-change negative control → Task 4. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; the one conditional (ancestors helper fallback) specifies the exact alternative. ✓

**Type consistency:** `ok`/`page`/`ok_list` signatures match `app/schemas/envelope.py`; schema names identical across tasks and tests (`ClanSummaryResponse`, `ClanDetailResponse`, `PlatformMetricsResponse`, `TreeResponse`, `TreeNodeDetail`, `RelationshipPathResponse`). Wire types (`str`/`str | None`) match the handler serializers verified in the spec. ✓
