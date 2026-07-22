# E2E HTTP Journey Harness (B1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** True HTTP-level journey tests on real Postgres with real RS256 JWT verification — founder lifecycle, multi-user collaboration (both membership paths), and loud KNOWN_DEFECT pins for H3/M9. Spec: `docs/superpowers/specs/2026-07-18-e2e-journeys-design.md`.

**Architecture:** One new module `backend/tests/integration/test_e2e_journeys.py` reusing `test_auth_http_flow.py`'s proven pattern: test RSA keypair → JWKS-cache injection (JWT verification runs for real), identity provider is the ONLY stubbed seam, `get_db` overridden to the migrated-DB sessionmaker, no lifespan, module-scoped app.

**Tech Stack:** pytest + TestClient + real Postgres (integration conftest), python-jose for JWT minting.

## Global Constraints

- **ZERO application code changes.** This PR touches exactly one new test file. If a journey stage surfaces a NEW defect (assertion contradicts reality for a route not already pinned), the implementer PINS current behavior with a `KNOWN_DEFECT_<slug>` name + docstring pointing at the review report, and REPORTS it — never adjusts app code, never silently weakens the intended assertion without the docstring.
- **No `dependency_overrides` on `get_current_user` or any handler** — only `get_db` and `get_identity_provider`.
- Envelope law asserted on every 2xx JSON hop: body keys are exactly `{"data"}` or `{"data", "meta"}`; errors are `{"error": {"code", "message", "detail"}}`.
- Rate-limit budget: module app instance shares 20 req/min/IP across `/api/v1/auth` + `/api/v1/invitations`. Planned spend: J1=2 auth, J2=3 auth + 2 invitations, J3=2 auth → **9 of 20**. The module docstring must carry this ledger (house pattern); update it if you add requests.
- Order-independence: every journey creates its own clan/users with uuid-suffixed slugs/emails; no test depends on another having run.
- Full gate before done: `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports`.

---

### Task 1: Module scaffolding + Journey 1 (founder lifecycle)

**Files:**
- Create: `backend/tests/integration/test_e2e_journeys.py`

**Interfaces:**
- Consumes: `migrated_db_url` fixture; `StubIdentityProvider` pattern from `tests/integration/test_auth_http_flow.py`.
- Produces: module fixtures (`rsa_keys`, `jwks_cache`, `stub_identity`, `client`) + helpers (`_auth`, `_mint`, `_envelope`, `_assert_hd`, `_register`, `_login`, `_create_person`) that Tasks 2–3 reuse.

- [ ] **Step 1: Create the module with fixtures and helpers**

```python
"""E2E HTTP journeys: full user stories over the real request path (B1).

Drives register → login → clan → persons → relationships → tree → export and the
multi-user collaboration story through TestClient against the migrated DB. JWT
verification is REAL (test keypair injected into the JWKS cache); the identity
provider is the only stubbed seam. This is the layer where the 2026-07-03 e2e
bugs (#12/#13) hid and where the tree routes' DI/serialization seam was never
exercised before (review 2026-07-18, test-posture gap #2).

KNOWN_DEFECT tests pin review findings the suite must keep visible until their
fix PR flips them: H3 (GET /tree 404s for API-managed clans) and M9 (malformed
cursor → 500).

Rate-limit budget: this module's app shares ONE 20 req/min/IP bucket across
/api/v1/auth + /api/v1/invitations. Current spend: J1=2 auth, J2=3 auth + 2
invitations, J3=2 auth → 9/20. Re-count before adding requests on those prefixes.
"""

import io
import json
import time
import uuid
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwk, jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.security as security_module
from app.core.database import get_db
from app.infrastructure.dependencies import get_identity_provider
from app.main import create_app

pytestmark = pytest.mark.integration

_KID = "e2e-journeys-key"
_PW = "Str0ng!pass-e2e"
```

Then copy — VERBATIM — from `tests/integration/test_auth_http_flow.py`: the `rsa_keys` fixture, the `jwks_cache` fixture, the `_issuer()` helper, and the full `StubIdentityProvider` class (it mints real RS256 tokens; keep every method). Only change `_KID` usages to this module's constant. Add:

```python
@pytest.fixture(scope="module")
def stub_identity(rsa_keys: dict[str, Any]) -> "StubIdentityProvider":
    return StubIdentityProvider(rsa_keys["private_pem"])


@pytest.fixture(scope="module")
def client(
    migrated_db_url: str, stub_identity: "StubIdentityProvider", jwks_cache: None
) -> Iterator[TestClient]:
    app = create_app()
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_identity_provider] = lambda: stub_identity
    yield TestClient(app)
    engine.sync_engine.dispose()


def _auth(token: str, clan_id: str | None = None) -> dict[str, str]:
    h = {"Authorization": f"Bearer {token}"}
    if clan_id:
        h["X-Current-Clan-Id"] = clan_id
    return h


def _mint(private_pem: str, user_id: uuid.UUID, email: str, full_name: str = "E2E") -> str:
    """OAuth-style account: a Supabase-verifiable JWT with no register call."""
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "iss": _issuer(),
        "iat": now,
        "exp": now + timedelta(hours=1),
        "user_metadata": {"full_name": full_name},
    }
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": _KID})


def _envelope(resp: Any, *, has_meta: bool = False) -> Any:
    """Assert the canonical success envelope; return data."""
    body = resp.json()
    assert set(body.keys()) == ({"data", "meta"} if has_meta else {"data"}), body
    if has_meta:
        assert set(body["meta"].keys()) == {"cursor", "has_more", "limit"}, body["meta"]
    return body["data"]


def _error_code(resp: Any) -> str:
    body = resp.json()
    assert set(body.keys()) == {"error"}, body
    assert {"code", "message", "detail"} <= set(body["error"].keys()), body
    return body["error"]["code"]


def _assert_hd(value: Any) -> None:
    """Assert a HistoricalDate object shape (ADR-011)."""
    assert isinstance(value, dict), value
    assert set(value.keys()) == {"date", "precision", "display", "lunar"}, value
    assert value["precision"] in ("exact", "year", "month", "circa", "unknown")


def _register_create(client: TestClient, email: str, slug: str, name: str) -> None:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": _PW,
            "full_name": name,
            "clan_action": "create",
            "clan_name": f"Clan {slug}",
            "clan_slug": slug,
        },
    )
    assert resp.status_code == 201, resp.text
    assert set(resp.json().keys()) == {"data"}


def _login(client: TestClient, email: str) -> tuple[str, dict[str, Any]]:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": _PW})
    assert resp.status_code == 200, resp.text
    data = _envelope(resp)
    return data["access_token"], data["user"]


def _create_person(
    client: TestClient, hdr: dict[str, str], full_name: str, gender: str, **extra: Any
) -> dict[str, Any]:
    resp = client.post(
        "/api/v1/persons", headers=hdr, json={"full_name": full_name, "gender": gender, **extra}
    )
    assert resp.status_code == 201, resp.text
    return _envelope(resp)
```

(If register requires email verification in the stub — check how `test_auth_http_flow.py` gets from register to login; mirror exactly whatever it does, e.g. no verification gate in the stub. If the export is a zip vs bare JSON, adapt the Journey-1 export stage per the actual `Content-Disposition`/content-type — the import list above includes `io`/`zipfile` in case; drop unused imports.)

- [ ] **Step 2: Write Journey 1**

```python
def test_journey_founder_lifecycle(
    client: TestClient, stub_identity: "StubIdentityProvider"
) -> None:
    """One founder's whole story over HTTP. Stages are labeled; a failure names
    its stage. Tree endpoints assert TODAY's truth for an API-managed clan
    (generation is null everywhere — H3; the GET /tree 404 itself is pinned in
    test_tree_unreachable_for_api_managed_clan_KNOWN_DEFECT_H3)."""
    suffix = uuid.uuid4().hex[:10]
    email = f"j1-{suffix}@ex.com"
    slug = f"j1-{suffix}"

    # Stage 1 — register (creates clan + admin membership)
    _register_create(client, email, slug, "Người Sáng Lập")

    # Stage 2 — login: tokens + profile with clan context
    token, user = _login(client, email)
    clan_id = user["clan_id"]
    assert user["role"] == "admin" and user["is_approved"] is True
    hdr = _auth(token, clan_id)

    # Stage 3 — /auth/me agrees with login; /me/clans is the canonical plain array
    me = _envelope(client.get("/api/v1/auth/me", headers=_auth(token)))
    assert me["clan_id"] == clan_id
    clans = _envelope(client.get("/api/v1/me/clans", headers=_auth(token)))
    assert [c["clan_id"] for c in clans] == [clan_id]
    sel = _envelope(client.post(f"/api/v1/me/clans/{clan_id}/select", headers=_auth(token)))
    assert sel["clan_id"] == clan_id

    # Stage 4 — build the family: ông, bà, con
    ong = _create_person(client, hdr, "Nguyễn Văn Tổ", "male", birth_date="1930-01-15")
    ba = _create_person(
        client, hdr, "Trần Thị Bà", "female",
        birth_date="1932-01-01", birth_date_precision="circa", birth_date_display="khoảng 1932",
    )
    con = _create_person(client, hdr, "Nguyễn Văn Con", "male", birth_date="1955-03-20")
    _assert_hd(ong["birth_date"])
    assert ba["birth_date"]["precision"] == "circa"
    assert ba["birth_date"]["display"] == "khoảng 1932"

    # Stage 5 — marriage + two biological edges
    mar = _envelope(
        client.post(
            "/api/v1/relationships/marriages",
            headers=hdr,
            json={"person1_id": ong["id"], "person2_id": ba["id"], "spouse_order": 1},
        )
    )
    _assert_hd(mar["marriage_date"])
    for parent in (ong, ba):
        edge = _envelope(
            client.post(
                "/api/v1/relationships/parent-child",
                headers=hdr,
                json={
                    "parent_id": parent["id"],
                    "child_id": con["id"],
                    "relationship_type": "biological",
                },
            )
        )
        assert edge["relationship_type"] == "biological"

    # Stage 6 — persons list: cursor-page envelope
    listing = client.get("/api/v1/persons", headers=hdr)
    assert listing.status_code == 200, listing.text
    people = _envelope(listing, has_meta=True)
    assert {p["id"] for p in people} == {ong["id"], ba["id"], con["id"]}

    # Stage 7 — tree read models over HTTP (the untested DI seam).
    # H3 truth: no founder is settable via the API, so đời cannot anchor —
    # generation is null on every node until A3 lands.
    focus = _envelope(client.get(f"/api/v1/tree/focus/{con['id']}", headers=hdr))
    assert focus["focus_person_id"] == con["id"]
    assert focus["generation_of_focus"] is None  # H3: no thủy tổ → đời unanchored
    ancestor_ids = {a["id"] for a in _envelope(
        client.get(f"/api/v1/tree/ancestors/{con['id']}", headers=hdr)
    )}
    assert {ong["id"], ba["id"]} <= ancestor_ids

    # Stage 8 — export the clan archive; the whole story must be inside
    exp = client.get("/api/v1/exports/clan?format=json", headers=hdr)
    assert exp.status_code == 200, exp.text
    assert "attachment" in exp.headers.get("content-disposition", "")
    archive = json.loads(exp.content)
    # Key names per app/application/export/handlers.py's archive builder —
    # verify there and adjust ONLY the key spelling if it differs:
    exported_person_ids = {p["id"] for p in archive["persons"]}
    assert {ong["id"], ba["id"], con["id"]} <= exported_person_ids
    assert len(archive["marriages"]) == 1
    assert len(archive["parent_child"]) == 2
```

If any stage's assertion contradicts reality (e.g. `/tree/ancestors` shape differs, export keys differ), verify against the handler code, adapt the ASSERTION to the actual current contract, and record every adaptation in your report. If a stage reveals genuinely broken behavior (5xx, wrong data), pin it as a KNOWN_DEFECT test with docstring + report it.

- [ ] **Step 3: Run Journey 1**

Run: `cd backend && uv run pytest tests/integration/test_e2e_journeys.py -v`
Expected: PASS (this journey asserts current behavior; H3's 404 is not hit here since Stage 7 uses explicit-person endpoints).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_e2e_journeys.py
git commit -m "test(e2e): founder lifecycle journey over HTTP — auth to tree to export"
```

---

### Task 2: Journey 2 (multi-user collaboration, both membership paths)

**Files:**
- Modify: `backend/tests/integration/test_e2e_journeys.py` (append)

**Interfaces:**
- Consumes: Task 1's fixtures/helpers (`client`, `stub_identity`, `rsa_keys`, `_auth`, `_mint`, `_envelope`, `_error_code`, `_register_create`, `_login`, `_create_person`).

- [ ] **Step 1: Write Journey 2**

```python
def test_journey_multiuser_collaboration(
    client: TestClient, stub_identity: "StubIdentityProvider", rsa_keys: dict[str, Any]
) -> None:
    """Admin + two joiners over HTTP: the invitation path (immediate approval)
    and the self-request path (pending → approve), then two-sided RBAC and a
    cross-clan isolation check."""
    suffix = uuid.uuid4().hex[:10]
    admin_email = f"j2a-{suffix}@ex.com"
    slug = f"j2-{suffix}"

    # Stage 1 — admin founds the clan
    _register_create(client, admin_email, slug, "Trưởng Tộc")
    admin_token, admin_user = _login(client, admin_email)
    clan_id = admin_user["clan_id"]
    admin_hdr = _auth(admin_token, clan_id)
    person = _create_person(client, admin_hdr, "Nguyễn Thị Gốc", "female")

    # Stage 2 — invitation path: viewer invited by email, accepts, approved at once
    invitee_email = f"j2v-{suffix}@ex.com"
    inv = _envelope(
        client.post(
            f"/api/v1/clans/{clan_id}/invitations",
            headers=admin_hdr,
            json={"email": invitee_email, "role": "viewer"},
        )
    )
    assert inv["role"] == "viewer" and inv["token"]
    # OAuth-style invitee: verifiable JWT, no register — the accept handler
    # provisions the profile itself (repo.ensure_profile).
    viewer_id = uuid.uuid4()
    viewer_token = _mint(rsa_keys["private_pem"], viewer_id, invitee_email, "Người Xem")
    acc = _envelope(
        client.post(f"/api/v1/invitations/{inv['token']}/accept", headers=_auth(viewer_token))
    )
    assert acc["clan_id"] == clan_id and acc["role"] == "viewer"

    # Stage 3 — two-sided RBAC over HTTP
    viewer_hdr = _auth(viewer_token, clan_id)
    ok = client.get("/api/v1/persons", headers=viewer_hdr)
    assert ok.status_code == 200, ok.text
    denied = client.post(
        "/api/v1/persons", headers=viewer_hdr, json={"full_name": "X", "gender": "male"}
    )
    assert denied.status_code == 403, denied.text
    assert _error_code(denied) == "insufficient_permissions"
    focus = _envelope(client.get(f"/api/v1/tree/focus/{person['id']}", headers=viewer_hdr))
    assert focus["focus_person_id"] == person["id"]  # viewer read access works

    # Stage 4 — self-request path: join → pending (person_id key present) → approve
    joiner_email = f"j2b-{suffix}@ex.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": joiner_email,
            "password": _PW,
            "full_name": "Người Xin Gia Nhập",
            "clan_action": "join",
            "clan_id": clan_id,
        },
    )
    assert resp.status_code == 201, resp.text
    pending = _envelope(
        client.get("/api/v1/clans/me/users/pending", headers=admin_hdr), has_meta=True
    )
    joiner_row = next(u for u in pending if u["email"] == joiner_email)
    assert "person_id" in joiner_row  # ADR-024: key present (null is fine)
    approved = client.post(
        f"/api/v1/clans/me/users/{joiner_row['user_id']}/approve", headers=admin_hdr
    )
    assert approved.status_code == 200, approved.text
    members = _envelope(client.get("/api/v1/clans/me/users", headers=admin_hdr), has_meta=True)
    assert any(u["email"] == joiner_email and u["is_approved"] for u in members)

    # Stage 5 — cross-clan isolation: a foreign X-Current-Clan-Id is rejected by
    # the membership check (same code path whether or not that clan exists).
    foreign = client.get("/api/v1/persons", headers=_auth(viewer_token, str(uuid.uuid4())))
    assert foreign.status_code == 403, foreign.text
    assert _error_code(foreign) == "clan_membership_required"
```

Adapt field names (`email`, `user_id`, `is_approved` in the pending/member rows) to the actual `ClanUserSummary` schema in `app/schemas/clan_membership.py` if they differ — adjust spelling only, never drop an assertion. Same pin-and-report rule for surprises.

- [ ] **Step 2: Run both journeys**

Run: `cd backend && uv run pytest tests/integration/test_e2e_journeys.py -v`
Expected: 2 PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_e2e_journeys.py
git commit -m "test(e2e): multi-user collaboration journey — both membership paths + RBAC"
```

---

### Task 3: Journey 3 — pinned defects (H3, M9) + i18n over HTTP

**Files:**
- Modify: `backend/tests/integration/test_e2e_journeys.py` (append)

- [ ] **Step 1: Write the pinned-defect and i18n tests**

```python
def test_tree_unreachable_for_api_managed_clan_KNOWN_DEFECT_H3(
    client: TestClient, stub_identity: "StubIdentityProvider"
) -> None:
    """PINS review finding H3 (docs/architecture/backend-review-2026-07-18.md):
    no API path can set is_founder (PersonCreateRequest has no such field; no
    membership PATCH exists), so find_clan_founder finds nothing and GET /tree
    404s for EVERY clan built through the API — the graph-computed đời feature
    cannot activate. PR A3 (founder designation) MUST flip this test to the
    desired behavior; this assertion failing is A3's RED signal, not a
    regression."""
    suffix = uuid.uuid4().hex[:10]
    email = f"j3-{suffix}@ex.com"
    _register_create(client, email, f"j3-{suffix}", "Chủ Tộc")
    token, user = _login(client, email)
    hdr = _auth(token, user["clan_id"])
    _create_person(client, hdr, "Nguyễn Văn Nhất", "male")

    resp = client.get("/api/v1/tree", headers=hdr)
    assert resp.status_code == 404, (
        "GET /tree no longer 404s — H3 has been fixed! Flip this test to assert "
        "the working tree (thủy tổ đời 1) and delete the KNOWN_DEFECT marker."
    )
    assert _error_code(resp) == "clan_founder_not_found"


def test_malformed_cursor_current_behavior_KNOWN_DEFECT_M9(
    client: TestClient, stub_identity: "StubIdentityProvider", rsa_keys: dict[str, Any]
) -> None:
    """PINS review finding M9: decode_cursor is unwrapped, so a garbage ?cursor=
    500s instead of returning 400 invalid_cursor. The M9 fix PR flips this to
    assert the 400. Uses Journey-3's clan via a fresh viewer-free admin JWT-less
    path: reuse any authed clan context — here we mint nothing new; the test
    creates its own minimal context to stay order-independent."""
    # NOTE: reuse the SAME clan as the H3 test would couple ordering; create a
    # minimal own context instead (0 extra auth-prefix requests: JWTs are minted,
    # membership seeded via the H3 pattern is NOT needed — a bare persons GET
    # with a malformed cursor fails in pagination BEFORE any row is read, but it
    # still requires a valid clan context, so we must have one).
    ...
```

**Implementer decision embedded here — resolve it concretely:** the M9 probe needs an authenticated user with an approved clan membership. To spend zero additional auth-prefix requests, mint a JWT for a NEW uuid user and seed the profile + clan + approved membership by direct SQL (same `_sync_engine` seeding style as `tests/integration/test_deactivation_invariant.py` — copy `_seed_profile`-style helpers, or import nothing and write the 3 INSERTs inline with a sync engine on `migrated_db_url.replace("+asyncpg", "")`... note the DSN may use `+psycopg`; `.replace("+asyncpg", "")` is a no-op then and `sa.create_engine` accepts `+psycopg`). Then:

```python
    resp = client.get("/api/v1/persons?cursor=%%%garbage%%%", headers=_auth(token, str(clan_id)))
    assert resp.status_code == 500, (
        "malformed cursor no longer 500s — M9 fixed! Flip to assert 400 invalid_cursor."
    )


def test_error_localization_over_http(
    client: TestClient, rsa_keys: dict[str, Any]
) -> None:
    """Accept-Language drives the REAL LanguageMiddleware: the same error yields
    an English message under `en` and falls back to Vietnamese for an
    unsupported locale. Uses an unauthenticated 401 (no budget, no seeding)."""
    r_en = client.get("/api/v1/persons", headers={"Accept-Language": "en"})
    assert r_en.status_code == 401
    msg_en = r_en.json()["error"]["message"]
    r_xx = client.get("/api/v1/persons", headers={"Accept-Language": "xx-YY"})
    msg_xx = r_xx.json()["error"]["message"]
    assert msg_en != msg_xx  # en differs from the vi fallback
    # Pin the exact strings against the i18n catalogs so a catalog rename fails loudly:
    # grep app/i18n/en.json and vi.json for the 401 code's key and assert equality.
```

Complete that last comment concretely: look up the 401 error code raised for a missing token (`missing_token` per `app/core/security.py::get_current_user`), find its message key in `app/i18n/en.json` / `vi.json`, and assert `msg_en == <exact en string>` and `msg_xx == <exact vi string>`.

- [ ] **Step 2: Run the whole module + count the budget**

Run: `cd backend && uv run pytest tests/integration/test_e2e_journeys.py -v`
Expected: 5 PASS. Re-count auth/invitations-prefix requests across the module and correct the docstring ledger if the real count differs from 9.

- [ ] **Step 3: Full suite regression**

Run: `cd backend && uv run pytest -q`
Expected: all pass (this module is additive; the shared rate-limit bucket is per app instance so other modules are unaffected).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_e2e_journeys.py
git commit -m "test(e2e): pin KNOWN_DEFECTs H3 (tree 404) + M9 (cursor 500); i18n over HTTP"
```

---

### Task 4: Full gate (controller-run)

- [ ] `cd backend && uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports` — all five green.
