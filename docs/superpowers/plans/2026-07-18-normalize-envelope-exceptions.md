# Normalize non-canonical envelope exceptions (ADR-024) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `GET /me/clans` and `GET /clans/me/users/pending` canonical, retiring ADR-024's two exceptions before the frontend binds.

**Architecture:** `/me/clans` → plain `ok_list(UserClanMembership)` (drop `meta.count`, breaking); `/clans/me/users/pending` → add `person_id` and reuse `ClanUserSummary` (additive). Drop the now-dead schemas + deprecation markers; mark ADR-024 normalized; update `docs/contracts`. Documentation-only OpenAPI typing stays doc-only; the only runtime change is the two response bodies.

**Tech Stack:** FastAPI, Pydantic v2, pytest. Commands from `backend/`.

## Global Constraints

- `/me/clans` returns `{"data": [...]}` — no `meta`. This IS a breaking change (drops `meta.count`) — intended, done pre-frontend. `docs/contracts/` is the spec and is updated in the same PR.
- `/pending` gains `person_id` (None-guarded, identical to the approved route) — additive.
- Documentation-only `responses=` (never `response_model=`). Coherence guards validate REAL route/handler output, sabotage-verified.
- After this, untyped-2xx (non-`/health`) stays exactly 1 (`/exports/clan`); no non-canonical exceptions remain.
- Line length 100. `uv run pytest`/`uv run mypy`; `uvx ruff`. Guards are `@pytest.mark.integration` → `docker compose up -d pgdb`.
- Branch `feat/normalize-envelope-exceptions` checked out. **Implementer scope discipline:** modify only the files each task names; no `.gitignore`, no `git push`, no PRs, no `git clean`.

---

### Task 1: `/me/clans` → plain `ok_list(UserClanMembership)`

**Files:** `app/application/me/handlers.py`, `app/api/v1/me.py`, `app/schemas/clan.py`, `tests/unit/api/test_openapi_typed_responses.py`, `tests/integration/test_me_and_platform_admin.py`

- [ ] **Step 1: Update the failing OpenAPI test**

In `tests/unit/api/test_openapi_typed_responses.py`, replace `test_me_clans_is_user_clans_envelope`:

```python
def test_me_clans_is_envelope_list_of_membership(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/me/clans", "get", "200")
    assert "Envelope" in ref and "UserClanMembership" in ref, ref
```

- [ ] **Step 2: Run it — verify it fails**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k me_clans -v`
Expected: FAIL — the route still declares `UserClansEnvelope`, so the ref lacks `UserClanMembership`.

- [ ] **Step 3: Simplify the handler to return a list**

In `app/application/me/handlers.py`, change `list_clans` to return the list directly (drop the `{clans, count}` wrapper). The method currently builds a list of dicts and returns `{"clans": <list>, "count": len(<list>)}`; change it to `return <list>` (keep the exact per-row dict mapping — `clan_id`/`clan_name`/`clan_slug`/`role`/`joined_at`). The return type annotation becomes `list[dict[str, Any]]`.

- [ ] **Step 4: Update the route**

In `app/api/v1/me.py`:
- Change the import `from app.schemas.clan import ClanSwitchResponse, UserClansEnvelope` → `from app.schemas.clan import ClanSwitchResponse, UserClanMembership`.
- Change the import `from app.schemas.envelope import ok` → `from app.schemas.envelope import ok, ok_list`.
- Replace the route:

```python
@router.get("/clans", responses=ok_list(UserClanMembership))
async def list_my_clans(
    current_user: dict[str, Any] = Depends(get_current_user),
    handler: MeQueryHandler = Depends(get_me_query_handler),
) -> dict[str, Any]:
    """List all clans the authenticated user belongs to (a clan switcher — all
    approved memberships, unpaginated)."""
    result = await handler.list_clans(user_id=current_user["sub"])
    return {"data": result}
```

- [ ] **Step 5: Drop the dead schemas**

In `app/schemas/clan.py`, remove `UserClansResponse` (unused — verified), `CountMeta`, and `UserClansEnvelope` (their only consumers were the route + guard being changed here). Keep `UserClanMembership` and `ClanSwitchResponse`.

- [ ] **Step 6: Verify the OpenAPI test passes**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k me_clans -v`
Expected: PASS.

- [ ] **Step 7: Update the behavior + coherence test**

In `tests/integration/test_me_and_platform_admin.py` (in `test_me_lists_only_approved_and_blocks_non_member`), the handler now returns a list. Replace the block that reads `clans["clans"]` / `clans["count"]` and the old coherence guard:

```python
        clans = await handler.list_clans(user_id=str(user_id))
        ids = {c["clan_id"] for c in clans}
        assert ids == {str(approved_clan)}  # only the approved membership
        assert len(clans) == 1

        # Coherence: the documented ok_list(UserClanMembership) must accept the real
        # wire body. /me/clans is a plain array now (no meta) — canonical, ADR-024 normalized.
        from app.schemas.clan import UserClanMembership

        body = {"data": clans}
        assert body["data"]  # non-empty
        for item in body["data"]:
            UserClanMembership.model_validate(item)  # raises on drift
```

- [ ] **Step 8: Run the coherence/behavior test + sabotage-check**

Requires pgdb. Run: `cd backend && uv run pytest tests/integration/test_me_and_platform_admin.py::test_me_lists_only_approved_and_blocks_non_member -v`
Expected: PASS. Sabotage-check: add a required field to `UserClanMembership` (e.g. `zzz: str`), confirm the guard FAILS, revert.

- [ ] **Step 9: Gate**

Run: `cd backend && uvx ruff format app/application/me/handlers.py app/api/v1/me.py app/schemas/clan.py && uvx ruff check app/application/me/handlers.py app/api/v1/me.py app/schemas/clan.py && uv run mypy app/application/me/handlers.py app/api/v1/me.py app/schemas/clan.py`
Expected: no errors.

- [ ] **Step 10: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add backend/app/application/me/handlers.py backend/app/api/v1/me.py backend/app/schemas/clan.py backend/tests/unit/api/test_openapi_typed_responses.py backend/tests/integration/test_me_and_platform_admin.py
git commit -m "feat(api)!: normalize /me/clans to a plain canonical array (ADR-024)

Drop the non-canonical meta:{count}; return {data:[UserClanMembership]} via
ok_list. Breaking (removes meta.count), done pre-frontend. Handler returns a
list; dead UserClansEnvelope/CountMeta/UserClansResponse removed.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 2: `/clans/me/users/pending` → add `person_id`, reuse `ClanUserSummary`

**Files:** `app/api/v1/clans.py`, `app/schemas/clan_membership.py`, `tests/unit/api/test_openapi_typed_responses.py`, `tests/integration/test_last_admin_race.py`

- [ ] **Step 1: Update the failing OpenAPI test**

In `tests/unit/api/test_openapi_typed_responses.py`, replace `test_clan_users_pending_is_page_envelope`:

```python
def test_clan_users_pending_is_page_envelope(openapi: dict[str, Any]) -> None:
    ref = _response_schema(openapi, "/api/v1/clans/me/users/pending", "get", "200")
    assert "PageEnvelope" in ref and "ClanUserSummary" in ref, ref
```

- [ ] **Step 2: Run it — verify it fails**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k clan_users_pending -v`
Expected: FAIL — the route still declares `PendingClanUser`.

- [ ] **Step 3: Add `person_id` to the pending route + retype it**

In `app/api/v1/clans.py`:
- Change the `list_pending_users` decorator `responses=page(PendingClanUser)` → `responses=page(ClanUserSummary)`.
- In the `list_pending_users` per-row dict, add the same None-guarded `person_id` the approved route uses, so the dict becomes:

```python
        {
            "id": str(u.id),
            "user_id": str(u.user_id),
            "role": u.role,
            # user_profile is eager-loaded via the same LEFT JOIN that serves the
            # approved list (SqlAlchemyClanRepository.list_users); None-guarded.
            "person_id": (
                str(u.user_profile.person_id)
                if u.user_profile is not None and u.user_profile.person_id
                else None
            ),
            "created_at": u.created_at.isoformat(),
        }
```

- Update the imports: remove `PendingClanUser` from the `from app.schemas.clan_membership import (...)` block (keep `ClanUserSummary`, `UserActionResponse`, `UserRoleChangeResponse`).

- [ ] **Step 4: Drop the `PendingClanUser` schema**

In `app/schemas/clan_membership.py`, remove the `PendingClanUser` class (and its legacy-exception docstring). `ClanUserSummary` now serves both routes.

- [ ] **Step 5: Verify the OpenAPI test passes**

Run: `cd backend && uv run pytest tests/unit/api/test_openapi_typed_responses.py -k clan_users_pending -v`
Expected: PASS.

- [ ] **Step 6: Update the coherence guard**

In `tests/integration/test_last_admin_race.py`:
- Change the import `from app.schemas.clan_membership import ClanUserSummary, PendingClanUser` → `from app.schemas.clan_membership import ClanUserSummary`.
- In the coherence guard (`test_clan_users_wire_matches_schemas` or similarly named), change the pending-rows validation from `PendingClanUser.model_validate(row)` to `ClanUserSummary.model_validate(row)`, and add an assertion that `person_id` is now present on the pending rows for the member with a linked person (i.e. at least one pending row has a non-None `person_id`). Approved-rows validation stays `ClanUserSummary`.

- [ ] **Step 7: Run the guard + sabotage-check**

Requires pgdb. Run the guard test by node id.
Expected: PASS. Sabotage-check: temporarily remove the `person_id` key from the pending dict in `clans.py` and confirm the new "pending has person_id" assertion FAILS, then revert.

- [ ] **Step 8: Gate**

Run: `cd backend && uvx ruff format app/api/v1/clans.py app/schemas/clan_membership.py tests/integration/test_last_admin_race.py && uvx ruff check app/api/v1/clans.py app/schemas/clan_membership.py tests/integration/test_last_admin_race.py && uv run mypy app/api/v1/clans.py app/schemas/clan_membership.py`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add backend/app/api/v1/clans.py backend/app/schemas/clan_membership.py backend/tests/unit/api/test_openapi_typed_responses.py backend/tests/integration/test_last_admin_race.py
git commit -m "feat(api): /clans/me/users/pending now includes person_id (ADR-024)

Additive — reuses the eager-loaded user_profile the approved list already joins.
pending shape now equals /clans/me/users, so PendingClanUser is dropped in favor
of ClanUserSummary.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 3: Retire ADR-024 + update contracts doc

**Files:** `docs/decisions/024-non-canonical-envelope-exceptions.md`, `docs/decisions/README.md`, `docs/contracts/README.md`

- [ ] **Step 1: Mark ADR-024 normalized**

In `docs/decisions/024-non-canonical-envelope-exceptions.md`, change the Status line:

```
## Status
Accepted (2026-07-18); **Normalized (2026-07-18)** — both exceptions retired:
`/me/clans` is now a plain canonical array (`ok_list`, no `meta:{count}`) and
`/clans/me/users/pending` now includes `person_id`. The intent recorded below is
fulfilled; this ADR is kept for the rationale/history.
```

- [ ] **Step 2: Update the ADR index status**

In `docs/decisions/README.md`, change the ADR-024 row's status column from `Accepted` to `Normalized`.

- [ ] **Step 3: Update the contracts caveat**

In `docs/contracts/README.md`, replace the passage naming the two non-canonical exceptions so it states that **all v1 JSON 2xx responses are canonical except `GET /exports/clan`** (file download, envelope-exempt), with no remaining non-canonical exceptions. (Find the current passage that mentions `/me/clans` (`meta:{count}`) and `/clans/me/users/pending` and ADR-024, and replace it with the exports-only statement.)

- [ ] **Step 4: Verify no stale "exception" references remain**

Run: `cd "/Volumes/Macext01 HD/playground/familyroots" && grep -rn "meta:{count}\|non-canonical\|legacy exception\|Do not copy\|LEGACY EXCEPTION" backend/app docs/contracts`
Expected: no matches in `backend/app` or `docs/contracts` (ADR-024 itself may still describe them historically — that's fine).

- [ ] **Step 5: Commit**

```bash
cd "/Volumes/Macext01 HD/playground/familyroots"
git add docs/decisions/024-non-canonical-envelope-exceptions.md docs/decisions/README.md docs/contracts/README.md
git commit -m "docs(adr): ADR-024 normalized — no non-canonical envelope exceptions remain

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DyucyzQosin6KZWM75Dm8p"
```

---

### Task 4: Full-suite verification

**Files:** none.

- [ ] **Step 1: Full gate**

Requires pgdb. Run:
```bash
cd "/Volumes/Macext01 HD/playground/familyroots/backend" && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports
```
Expected: all green.

- [ ] **Step 2: OpenAPI shape check**

Run:
```bash
cd "/Volumes/Macext01 HD/playground/familyroots/backend" && uv run python -c "
from app.main import create_app
spec = create_app().openapi()
# untyped-2xx still exactly 1 (/exports/clan)
untyped = []
for path, ops in spec['paths'].items():
    if path == '/health': continue
    for method, op in ops.items():
        for code, resp in op.get('responses', {}).items():
            if not str(code).startswith('2'): continue
            c = resp.get('content', {})
            if not c: continue
            s = c.get('application/json', {}).get('schema', {})
            if '\$ref' not in s and 'allOf' not in s and 'items' not in s:
                untyped.append((method.upper(), path, code))
assert untyped == [('GET','/api/v1/exports/clan','200')], untyped
# /me/clans is now an Envelope[list[UserClanMembership]]; /pending is PageEnvelope[ClanUserSummary]
me = spec['paths']['/api/v1/me/clans']['get']['responses']['200']['content']['application/json']['schema']['\$ref']
pend = spec['paths']['/api/v1/clans/me/users/pending']['get']['responses']['200']['content']['application/json']['schema']['\$ref']
assert 'UserClanMembership' in me and 'Envelope' in me, me
assert 'ClanUserSummary' in pend and 'PageEnvelope' in pend, pend
# dropped schemas are gone from components
comps = spec['components']['schemas']
for dead in ('UserClansEnvelope','CountMeta','PendingClanUser'):
    assert not any(dead in k for k in comps), dead
print('OK: /me/clans ok_list, /pending ClanUserSummary, dead schemas gone, only /exports/clan untyped')
"
```
Expected: `OK: ...`.

---

## Self-Review

**Spec coverage:**
- `/me/clans` → `ok_list(UserClanMembership)`, handler returns list, dead schemas dropped → Task 1. ✓
- `/pending` → `page(ClanUserSummary)` + `person_id`, `PendingClanUser` dropped → Task 2. ✓
- ADR-024 normalized + index + contracts caveat → Task 3. ✓
- Guards updated + sabotage-verified; `count`-test flipped to `len` (negative control) → Task 1 Step 7. ✓
- Full gate + OpenAPI shape assertions (dead schemas gone, only `/exports/clan` untyped) → Task 4. ✓

**Placeholder scan:** every code/edit step shows literal code or an exact locate-and-replace instruction; no TBD/TODO.

**Type consistency:** `ok_list`/`page` match `envelope.py`; `UserClanMembership` (clan.py:9), `ClanUserSummary` (clan_membership.py) are reused/kept; `UserClansEnvelope`/`CountMeta`/`UserClansResponse`/`PendingClanUser` are consistently removed across route, schema, tests, and OpenAPI assertions.
