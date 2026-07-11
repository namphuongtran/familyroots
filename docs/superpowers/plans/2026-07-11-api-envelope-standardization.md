# API Success-Envelope Standardization (F-1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every 2xx JSON body `{"data": ...}` (lists add `"meta": {cursor, has_more, limit}`), so the API has one success-envelope + one pagination meta shape.

**Architecture:** Explicit per-route wrapping (no middleware — matches the codebase). Wrap the 19 non-conforming routes; move adjuncts (batch errors, parent-child warning) into `meta`; wrap auth tokens; convert claims lists to the cursor helper; expose the standard meta on `GET /persons`. Grouped by router so each task is independently reviewable with a bounded test surface, and no route is touched twice.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, `app/core/pagination.py` (cursor helper), pytest-asyncio.

## Global Constraints

- **Canonical:** every 2xx JSON body is `{"data": <payload>}`; list endpoints add `"meta": {"cursor": str|null, "has_more": bool, "limit": int}`; 204s have no body; `GET /health` is EXEMPT (do not touch).
- **Meta SHAPE is uniform; cursor encoding is per-endpoint/opaque.** Claims uses the `created_at`-ASC helper (`paginate_query`/`build_page`). Persons keeps its **alphabetical (`full_name`) order and id-cursor**, only now exposing the standard meta (fetch `limit+1` for `has_more`, `cursor` = last id). Do NOT re-order persons by `created_at`.
- **Adjuncts go in `meta`**, never as top-level siblings: `persons/batch` → `meta.errors`; `parent-child` advisory → `meta.warning` (omit `meta` when there is no warning).
- **Auth tokens wrap**: login/register/onboard/refresh → `{"data": {...}}`. `login`'s data carries `user`; `refresh` is tokens-only.
- **`GET /persons` drops the bare `total`** (cursor pagination has no total). **Claims lists flip to oldest-first (ASC)** — the shared helper is ASC-only (owner-approved).
- **Behavior unchanged** — only the response *shape* changes (auth/claim/invitation logic untouched).
- **Retire** `IdentityClaimPaginatedResponse`; routes stop using per-model `response_model` for wrapped routes and return `dict[str, Any]`.
- **Tests:** each task updates the tests for the routers it changes; the FULL suite gate is the safety net (run `uv run pytest`, not just the task's files — SP-2B lesson).
- **Quality gate (full, every task)** from `backend/`: `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` (use `uv run mypy`, NOT bare `uvx mypy`). All pass before commit.

---

## Task 1: auth router → `{data}`

**Files:** Modify `backend/app/api/v1/auth.py`; update auth tests (`tests/integration/test_auth_http_flow.py`, `tests/unit/**` asserting auth shapes, `tests/unit/api/test_resend_verification.py` already conforms).

**Changes (each: change return-type annotation to `dict[str, Any]`, wrap the result):**
- `register` (`auth.py:41-54`): `result = await handler.register(...)` → `return {"data": result.model_dump()}`.
- `onboard` (`auth.py:57-72`): `result = await handler.onboard_authenticated_user(...)` → `return {"data": result.model_dump()}`.
- `login` (`auth.py:75-80`): `result = await handler.login(...)` → `return {"data": result.model_dump()}` (result is `LoginResponse`; `data` includes nested `user`).
- `refresh` (`auth.py:94-100`): `result = await svc.refresh_token(...)` (already a dict) → `return {"data": result}`.
- `logout` (`auth.py:83-91`): `return {"data": {"message": t("auth.logged_out")}}`.

- [ ] **Step 1: Write/adjust the failing tests**

In `tests/integration/test_auth_http_flow.py`, update the register→login→me flow assertions to the enveloped shape. Example for the login assertion:

```python
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "secret123"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"data"}                      # enveloped
    assert body["data"]["access_token"]
    assert body["data"]["user"]["email"] == email            # login carries user
```

Add a focused refresh + logout envelope assertion:

```python
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": "stub-refresh"})
    assert r.json().keys() == {"data"} and "access_token" in r.json()["data"]
    lo = client.post("/api/v1/auth/logout", headers=auth_header)
    assert lo.json() == {"data": {"message": lo.json()["data"]["message"]}}  # shape only
```

(Adapt to the file's actual fixtures/helpers; the binding assertion is: register/login/refresh/logout bodies are `{"data": ...}` with the token fields under `data`.)

- [ ] **Step 2: Run to verify they fail** — `cd backend && uv run pytest tests/integration/test_auth_http_flow.py -xvs` → FAIL (bodies still flat).
- [ ] **Step 3: Apply the route changes** (above).
- [ ] **Step 4: Run the auth tests green** — `uv run pytest tests/integration/test_auth_http_flow.py -v`.
- [ ] **Step 5: Full gate** — fix any OTHER test across the suite that asserted the old flat auth shape (grep `access_token"]` / `["user_id"]` on auth responses). `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.
- [ ] **Step 6: Commit** — `git add app/api/v1/auth.py tests/…` ; `git commit -m "refactor(backend): auth responses use {data} envelope (F-1)"`.

---

## Task 2: me router → `{data}`

**Files:** Modify `backend/app/api/v1/me.py`; update `tests/integration/test_me_and_platform_admin.py` (+ any me assertions).

**Changes (wrap at the route; handler unchanged):**
- `list_my_clans` (`me.py:16-22`): `result = await handler.list_clans(...)` → `return {"data": result["clans"], "meta": {"count": result["count"]}}`.
- `select_clan` (`me.py:25-31`): `result = await handler.select_clan(...)` → `return {"data": result}`.

- [ ] **Step 1: Failing tests** — in `test_me_and_platform_admin.py`, `list_clans` assertions become:

```python
    clans = await handler.list_clans(user_id=str(user_id))   # handler unit stays {clans,count}
    # route-level (if exercised via client): body == {"data": [...], "meta": {"count": 1}}
```

If the file tests the handler directly (not the route), the handler's return is unchanged — add/adjust a route-level assertion where the client is used; otherwise assert the wrapping in a small route test mirroring `tests/unit/api/test_tree_focus_endpoint.py` (FastAPI + `me.router` + `dependency_overrides[get_current_user]` + a fake `MeQueryHandler`).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Apply route changes.**
- [ ] **Step 4: me tests green.**
- [ ] **Step 5: Full gate** (grep for `["clans"]` / `["count"]` assertions on the me response).
- [ ] **Step 6: Commit** — `git add app/api/v1/me.py tests/…` ; `"refactor(backend): me responses use {data}/{data,meta} envelope (F-1)"`.

---

## Task 3: claims router — wrap + convert both lists to cursor `meta`

**Files:** Modify `backend/app/api/v1/claims.py`, `backend/app/application/person/claim_handlers.py`, `backend/app/infrastructure/persistence/claim_repository.py`, `backend/app/domain/person/claim_repository.py` (ClaimQueryPort), `backend/app/schemas/claim.py` (retire `IdentityClaimPaginatedResponse`); update `tests/integration/test_list_my_claims.py`, `tests/unit/api/test_list_my_claims_endpoint.py`, `tests/unit/api/test_claims_clan_guard.py`, and any admin-claims-list test.

**Interfaces (after):**
- `ClaimQueryPort.list_clan_claims(clan_id, status, cursor, limit) -> list[ClaimModel]` (up to `limit+1` rows via `paginate_query`); same for `list_user_claims(user_id, status, cursor, limit)`.
- `ClaimQueryHandler.list_clan_claims(*, clan_id, status=None, cursor=None, limit=20) -> dict[str, Any]` returns `{"data": [IdentityClaimResponse dict...], "meta": {...}}`; same for `list_my_claims`.

- [ ] **Step 1: Write the failing tests** — rewrite the claims list tests for the cursor shape. Example (`test_list_my_claims.py`):

```python
    result = await handler.list_my_claims(user_id=user_a)
    assert set(result.keys()) == {"data", "meta"}
    assert {c["user_id"] for c in result["data"]} == {str(user_a)}
    assert result["meta"]["has_more"] is False and result["meta"]["limit"] == 20
    # paging: seed >limit claims, first page has_more True + a cursor, second page via cursor advances
```

Update `test_list_my_claims_endpoint.py`: the fake handler returns `{"data": [...], "meta": {...}}`; the route param is `cursor`/`limit` (not page/page_size); 422 on `limit=0`/`limit=101`.

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Convert the query port (protocol + impl).** In `claim_repository.py`, replace `list_clan_claims` body:

```python
    async def list_clan_claims(
        self, clan_id: uuid.UUID, status: str | None, cursor: str | None, limit: int
    ) -> list[ClaimModel]:
        query = (
            select(ClaimModel)
            .join(Person, ClaimModel.person_id == Person.id)
            .where(Person.created_by_clan_id == clan_id)
        )
        if status:
            query = query.where(ClaimModel.status == status)
        query = paginate_query(query, ClaimModel, cursor, limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_user_claims(
        self, user_id: uuid.UUID, status: str | None, cursor: str | None, limit: int
    ) -> list[ClaimModel]:
        query = select(ClaimModel).where(ClaimModel.user_id == user_id)
        if status:
            query = query.where(ClaimModel.status == status)
        query = paginate_query(query, ClaimModel, cursor, limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())
```

Add `from app.core.pagination import build_page, paginate_query` (build_page used by the handler; import where used). Update the `ClaimQueryPort` protocol signatures in `app/domain/person/claim_repository.py` to `(..., cursor: str | None, limit: int) -> list[Any]`.

- [ ] **Step 4: Convert the handler.** In `claim_handlers.py`, `ClaimQueryHandler`:

```python
    async def list_clan_claims(
        self, *, clan_id: uuid.UUID, status: str | None = None,
        cursor: str | None = None, limit: int = 20,
    ) -> dict[str, Any]:
        claims = await self._query_port.list_clan_claims(clan_id, status, cursor, limit)
        page = build_page(claims, limit)
        return {
            "data": [IdentityClaimResponse.model_validate(c).model_dump() for c in page["data"]],
            "meta": page["meta"],
        }

    async def list_my_claims(
        self, *, user_id: uuid.UUID, status: str | None = None,
        cursor: str | None = None, limit: int = 20,
    ) -> dict[str, Any]:
        claims = await self._query_port.list_user_claims(user_id, status, cursor, limit)
        page = build_page(claims, limit)
        return {
            "data": [IdentityClaimResponse.model_validate(c).model_dump() for c in page["data"]],
            "meta": page["meta"],
        }
```

Add `from app.core.pagination import build_page` + `from typing import Any` as needed. Remove the `IdentityClaimPaginatedResponse` import/usage.

- [ ] **Step 5: Convert the routes + wrap the mutations.** In `claims.py`:
  - `list_my_claims` (`GET /claims`): params → `status: str | None = Query(None)`, `cursor: str | None = Query(None)`, `limit: int = Query(20, ge=1, le=100)`; `return await handler.list_my_claims(user_id=user.id, status=status, cursor=cursor, limit=limit)` (already enveloped by the handler).
  - `list_clan_claims` (`GET /clans/{cid}/claims`): same param change; `result = await handler.list_clan_claims(clan_id=clan_id, status=status, cursor=cursor, limit=limit)`; preserve `?fields=` by filtering `result["data"]`: `if fields: result["data"] = filter_list(result["data"], parse_field_set(fields))`; `return result`.
  - `approve_claim` / `reject_claim` / `prelink_identity`: remove `response_model=IdentityClaimResponse`, change return annotation to `dict[str, Any]`, `result = await handler.<method>(...)` → `return {"data": result.model_dump()}` (keep `prelink` at 201).

- [ ] **Step 6: Retire the schema.** In `app/schemas/claim.py`, delete `IdentityClaimPaginatedResponse` (grep-confirm no remaining import).

- [ ] **Step 7: Run tests green** — `uv run pytest tests/integration/test_list_my_claims.py tests/unit/api/test_list_my_claims_endpoint.py tests/unit/api/test_claims_clan_guard.py -v`.
- [ ] **Step 8: Full gate** (fix any other claim-shape assertion in the suite).
- [ ] **Step 9: Commit** — `"refactor(backend): claims responses use {data}/{data,meta} cursor pagination (F-1)"`.

---

## Task 4: invitations router → `{data}`

**Files:** Modify `backend/app/api/v1/invitations.py`; update invitation tests.

**Changes:**
- `create_invitation`: remove `response_model=InvitationCreatedResponse`, annotate `-> dict[str, Any]`, `out = await handler.create(...)` → `return {"data": InvitationCreatedResponse.model_validate(out).model_dump()}` (keep 201).
- `accept_invitation`: remove `response_model=InvitationAcceptedResponse`, annotate `-> dict[str, Any]`, build the response then `return {"data": InvitationAcceptedResponse(clan_id=out["clan_id"], role=out["role"], message=t("invitation.accepted")).model_dump()}`.

(`list_invitations` already returns `{"data": [...]}` — leave it.)

- [ ] **Step 1: Failing tests** — update the invitation create/accept assertions to `body["data"][...]` (token/accept_path under `data`; clan_id/role/message under `data`).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Apply changes.**
- [ ] **Step 4: invitation tests green.**
- [ ] **Step 5: Full gate.**
- [ ] **Step 6: Commit** — `"refactor(backend): invitation responses use {data} envelope (F-1)"`.

---

## Task 5: persons + relationships — meta pagination, adjuncts→meta, claim wrap

**Files:** Modify `backend/app/api/v1/persons.py`, `backend/app/application/person/handlers.py`, `backend/app/infrastructure/persistence/person_repository.py`, `backend/app/api/v1/relationships.py`; update persons + relationships tests.

**5a — `GET /persons` → `{data, meta}` (standard shape; keep alphabetical order + id-cursor):**
- `person_repository.list_in_clan`: change the final `.limit(limit)` to `.limit(limit + 1)` (fetch one extra to detect `has_more`).
- `person handlers.list_persons`: stop returning `total`; return `(data, meta)`:

```python
    async def list_persons(self, query: ListPersons) -> tuple[list[PersonResponse], dict[str, Any]]:
        filters = PersonFilters(gender=query.gender, generation=query.generation, is_deleted=False)
        rows = await self._repo.list_in_clan(query.clan_id, filters, query.cursor, query.limit)
        has_more = len(rows) > query.limit
        page = rows[: query.limit]
        meta = {
            "cursor": str(page[-1].id) if has_more and page else None,
            "has_more": has_more,
            "limit": query.limit,
        }
        return [PersonResponse.model_validate(p) for p in page], meta
```

(Drop the `count_in_clan`/`total` line from this method; leave `count_in_clan` in the repo — other callers may use it. NOTE: the pre-existing name-order-vs-id-cursor mismatch in `list_in_clan` is a KNOWN pagination-stability bug, orthogonal to this envelope change — do NOT fix it here; it's a documented follow-up.)
- `persons.py` list route: `persons, meta = await handler.list_persons(...)`; build `res_data` as today; `return {"data": res_data, "meta": meta}` (replace the `{"data": res_data, "total": total}` return).

**5b — `POST /persons/batch` → `meta.errors`:**
- `persons.py:318`: `return {"data": data, "meta": {"errors": errors}}`.

**5c — `POST /persons/{id}/claim` → wrap:**
- remove `response_model=IdentityClaimResponse`, annotate `-> dict[str, Any]`, `result = await handler.submit_claim(...)` → `return {"data": result.model_dump()}` (keep 201).

**5d — `POST /relationships/parent-child` → `meta.warning`:**
- `relationships.py:153-156`:

```python
    response: dict[str, Any] = {"data": link.model_dump()}
    if warning:
        response["meta"] = {"warning": warning}
    return response
```

- [ ] **Step 1: Failing tests** — persons list test asserts `{"data":[...], "meta": {"cursor", "has_more", "limit"}}` and NO `total`; add a real-DB paging test (seed >limit persons → page 1 `has_more True` + cursor → page 2 via cursor). batch test asserts `meta.errors`. parent-child test asserts `meta.warning` (present only when a warning fires). claim-submit test asserts `body["data"]`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Apply 5a–5d.**
- [ ] **Step 4: persons + relationships tests green** — `uv run pytest tests/integration/test_persons*.py tests/unit/api/test_persons_batch_endpoint.py tests/…relationship… -v`.
- [ ] **Step 5: Full gate** (fix any other `["total"]`/`["errors"]`/`["warning"]` assertions).
- [ ] **Step 6: Commit** — `"refactor(backend): persons meta pagination + adjuncts→meta + claim wrap; parent-child warning→meta (F-1)"`.

---

## Task 6: contract docs

**Files:** Modify `docs/contracts/README.md` + the affected per-surface docs.

- Add a top-level **"Response envelope"** section to `docs/contracts/README.md`: state the canonical rule (every 2xx = `{"data": ...}`; lists add `"meta": {cursor, has_more, limit}`; 204 no body; `/health` exempt; adjuncts in `meta`).
- Correct the shape examples in `rest-auth-api.md` (tokens under `data`), `rest-me-api.md` (`data`+`meta.count`), `rest-persons-api.md` (`data`+`meta`, no `total`), `rest-claims-api.md` (`data`+`meta` cursor; params `cursor`/`limit`), invitations, and any doc showing a bare-model/`items,total,page,page_size` shape.

- [ ] **Step 1:** Update `README.md` envelope section.
- [ ] **Step 2:** Correct each per-surface doc's response examples.
- [ ] **Step 3: Gate** — `uvx ruff format --check .` (docs don't affect pytest, but run the full gate once for safety): `uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.
- [ ] **Step 4: Commit** — `git add ../docs/contracts/*.md` ; `"docs(contracts): document {data}/{data,meta} response envelope (F-1)"`.

---

## Self-Review

**1. Spec coverage:** all 19 non-conforming routes are addressed — auth 5 (T1), me 2 (T2), claims 5 [3 wrap + 2 list-cursor] (T3), invitations 2 (T4), persons 3 [list-meta + batch + claim] + relationships 1 (T5); contract docs (T6). `/health` exempt (untouched). ✅
**2. Placeholder scan:** route changes give exact before→after; the two pagination conversions give full code; test steps specify the binding assertions and say to adapt to each file's fixtures (a real constraint, not a logic placeholder). ✅
**3. Type consistency:** wrapped routes return `dict[str, Any]` (drop per-model `response_model`); `list_persons` returns `(list[PersonResponse], dict)`; claim query port + handler use `(…, cursor, limit)` and return `{"data", "meta"}` consistently; `paginate_query`/`build_page` signatures match `app/core/pagination.py`. ✅
**Known pre-existing issue flagged (not fixed here):** `person_repository.list_in_clan` orders by `full_name` but cursors on `id` — a pagination-stability bug orthogonal to the envelope; documented follow-up.
