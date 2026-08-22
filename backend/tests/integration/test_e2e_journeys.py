"""E2E HTTP journeys: full user stories over the real request path (B1).

Drives register → login → clan → persons → relationships → tree → export and the
multi-user collaboration story through TestClient against the migrated DB. JWT
verification is REAL (test keypair injected into the JWKS cache); the identity
provider is the only stubbed seam. This is the layer where the 2026-07-03 e2e
bugs (#12/#13) hid and where the tree routes' DI/serialization seam was never
exercised before (review 2026-07-18, test-posture gap #2).

KNOWN_DEFECT tests pinned review findings until their fix PR flipped them.
Both are now CLOSED: M9 (malformed cursor → 400 invalid_cursor) by the
cursor-400 PR — see test_malformed_cursor_returns_400_invalid_cursor; H3
(GET /tree 404s for API-managed clans) by PR A3 — see
test_tree_renders_after_founder_designation and
test_tree_404_without_founder_designation. No KNOWN_DEFECT pins remain.

Rate-limit budget: this module's app shares ONE 20 req/min/IP bucket across
/api/v1/auth + /api/v1/invitations — matched by path PREFIX, so GET /auth/me
counts too (RateLimitMiddleware.dispatch: `request.url.path.startswith(p)`, see
app/core/rate_limit.py). Note the admin invitation-create call is
POST /api/v1/clans/{clan_id}/invitations — that path starts with /api/v1/clans,
NOT /api/v1/invitations, so it does NOT count against this bucket; only
POST /api/v1/invitations/{token}/accept does. PUT /api/v1/clans/me/founder is
also under /api/v1/clans, not /api/v1/auth or /api/v1/invitations — it spends
ZERO budget. Current spend: J1=3 auth (register, login, /auth/me), J2=3 auth
(admin register, admin login, joiner register) + 1 invitation (accept only —
create does not match the prefix), test_tree_renders_after_founder_designation
=2 auth (register, login; the founder designation PUT itself is free) +
test_tree_404_without_founder_designation=2 auth (register, login) → 10 auth +
1 invitation = 11/20. The M9 and i18n tests below add ZERO: M9 mints its JWT
directly against a SQL-seeded clan (no /auth/* call at all), and the i18n
test's unauthenticated GET /api/v1/persons never touches the /api/v1/auth or
/api/v1/invitations prefixes. Re-count before adding requests on those
prefixes.
"""

import json
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwk, jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.security as security_module
from app.core.database import get_db, get_system_db
from app.domain.auth.identity_provider import (
    AuthenticatedIdentity,
    AuthTokens,
    IdentityAuthError,
    IdentityUserExistsError,
)
from app.infrastructure.dependencies import get_identity_provider
from app.main import create_app

pytestmark = pytest.mark.integration

_KID = "e2e-journeys-key"
_PW = "Str0ng!pass-e2e"


@pytest.fixture(scope="module")
def rsa_keys() -> dict[str, Any]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    public_jwk = jwk.construct(public_pem, "RS256").to_dict()
    public_jwk.update({"kid": _KID, "use": "sig", "alg": "RS256"})
    return {"private_pem": private_pem, "jwks": {"keys": [public_jwk]}}


@pytest.fixture(scope="module")
def jwks_cache(rsa_keys: dict[str, Any]) -> Iterator[None]:
    """Prime the JWKS cache with the test public key so token verification runs
    the real code path without a network fetch."""
    old_cache, old_time = security_module._jwks_cache, security_module._jwks_cache_time
    security_module._jwks_cache = rsa_keys["jwks"]
    security_module._jwks_cache_time = time.monotonic()
    yield
    security_module._jwks_cache, security_module._jwks_cache_time = old_cache, old_time


def _issuer() -> str:
    # Must match what verify_supabase_token derives from the settings object it
    # actually holds (module-level import), whatever .env says.
    return f"{security_module.settings.SUPABASE_URL.rstrip('/')}/auth/v1"  # type: ignore[attr-defined]


class StubIdentityProvider:
    """In-memory IdentityProvider that mints verifiable RS256 JWTs."""

    def __init__(self, private_pem: str) -> None:
        self._private_pem = private_pem
        self._users: dict[str, dict[str, str]] = {}  # email -> {id, password, full_name}
        self.verification_emails: list[str] = []
        self.password_resets: list[str] = []

    def _mint(self, user_id: str, email: str, full_name: str) -> str:
        now = datetime.now(UTC)
        claims = {
            "sub": user_id,
            "email": email,
            "aud": "authenticated",
            "iss": _issuer(),
            "iat": now,
            "exp": now + timedelta(hours=1),
            "user_metadata": {"full_name": full_name},
        }
        return jwt.encode(claims, self._private_pem, algorithm="RS256", headers={"kid": _KID})

    async def create_user(self, *, email: str, password: str) -> str:
        if email in self._users:
            raise IdentityUserExistsError(email)
        user_id = str(uuid.uuid4())
        self._users[email] = {"id": user_id, "password": password, "full_name": ""}
        return user_id

    async def delete_user(self, user_id: str) -> None:
        self._users = {e: u for e, u in self._users.items() if u["id"] != user_id}

    async def sign_in(self, *, email: str, password: str) -> AuthenticatedIdentity:
        user = self._users.get(email)
        if user is None or user["password"] != password:
            raise IdentityAuthError("invalid credentials")
        access = self._mint(user["id"], email, user["full_name"])
        return AuthenticatedIdentity(
            user_id=user["id"],
            email=email,
            full_name=user["full_name"],
            tokens=AuthTokens(access_token=access, refresh_token="stub-refresh", expires_in=3600),
        )

    async def refresh(self, *, refresh_token: str) -> AuthTokens:
        if refresh_token != "stub-refresh":
            raise IdentityAuthError("bad refresh token")
        return AuthTokens(access_token="new-access", refresh_token="stub-refresh", expires_in=3600)

    async def sign_out(self, *, access_token: str) -> None:
        return None

    async def update_user(
        self, *, user_id: str, full_name: str | None, preferred_locale: str | None
    ) -> None:
        return None

    async def send_verification_email(self, *, email: str) -> None:
        self.verification_emails.append(email)

    async def send_password_reset(self, *, email: str) -> None:
        self.password_resets.append(email)


@pytest.fixture(scope="module")
def stub_identity(rsa_keys: dict[str, Any]) -> StubIdentityProvider:
    return StubIdentityProvider(rsa_keys["private_pem"])


@pytest.fixture(scope="module")
def client(
    migrated_db_url: str, stub_identity: StubIdentityProvider, jwks_cache: None
) -> Iterator[TestClient]:
    app = create_app()
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    # ADR-048: POST /invitations/{token}/accept runs on the privileged system session
    # (it has no clan context), so the test session must be injected there too.
    app.dependency_overrides[get_system_db] = _override_db
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
    assert set(body["error"].keys()) == {"code", "message", "detail"}, body
    return cast(str, body["error"]["code"])


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
    return cast(dict[str, Any], _envelope(resp))


def test_journey_founder_lifecycle(client: TestClient, stub_identity: StubIdentityProvider) -> None:
    """One founder's whole story over HTTP. Stages are labeled; a failure names
    its stage. Ông is designated thủy tổ after Stage 5 (PUT /clans/me/founder,
    ADR-026/A3), so đời anchors off him for the rest of the journey: ông đời 1,
    con đời 2 (docs/architecture/tree-read-model.md)."""
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
        client,
        hdr,
        "Trần Thị Bà",
        "female",
        birth_date="1932-01-01",
        birth_date_precision="circa",
        birth_date_display="khoảng 1932",
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

    # Stage 5b — designate ông as thủy tổ (ADR-026 / A3): admin-only, anchors đời.
    designation = _envelope(
        client.put(
            "/api/v1/clans/me/founder",
            headers=hdr,
            json={"person_id": ong["id"]},
        )
    )
    assert designation["person_id"] == ong["id"]
    assert designation["previous_person_id"] is None

    # Stage 6 — persons list: cursor-page envelope
    listing = client.get("/api/v1/persons", headers=hdr)
    assert listing.status_code == 200, listing.text
    people = _envelope(listing, has_meta=True)
    assert {p["id"] for p in people} == {ong["id"], ba["id"], con["id"]}
    ong_row = next(p for p in people if p["id"] == ong["id"])
    assert ong_row["full_name"] == "Nguyễn Văn Tổ"
    _assert_hd(ong_row["birth_date"])
    assert ong_row["birth_date"]["date"] == "1930-01-15"

    # Stage 7 — tree read models over HTTP (the untested DI seam).
    # Ông was designated thủy tổ in Stage 5b: ông đời 1, con đời 2.
    focus = _envelope(client.get(f"/api/v1/tree/focus/{con['id']}", headers=hdr))
    assert focus["focus_person_id"] == con["id"]
    assert focus["generation_of_focus"] == 2  # con: ông đời 1 → con đời 2
    # focus_subtree's root IS con himself (app/schemas/tree.py FocusTreeNode);
    # mother_id lives directly on that node — con's biological mother is bà
    # (đa thê attribution), not a nested field. Verified against
    # app/services/tree_builder.py (mother_id keyed per-node by the child's own
    # biological mother, not the marriage/spouse side).
    assert focus["focus_subtree"]["id"] == con["id"]
    assert focus["focus_subtree"]["mother_id"] == ba["id"]

    ancestors = _envelope(client.get(f"/api/v1/tree/ancestors/{con['id']}", headers=hdr))
    # Live payload includes the focus person itself at depth 0 (GetAncestors
    # handler returns the full chain, not just strict ancestors) — assert the
    # EXACT id set rather than a superset.
    assert {a["id"] for a in ancestors} == {con["id"], ong["id"], ba["id"]}
    ong_node = next(a for a in ancestors if a["id"] == ong["id"])
    _assert_hd(ong_node["birth_date"])
    assert ong_node["birth_date"]["date"] == "1930-01-15"
    assert ong_node["full_name"] == "Nguyễn Văn Tổ"
    assert ong_node["generation"] == 1  # ông is thủy tổ

    # Stage 8 — export the clan archive; the whole story must be inside.
    # Envelope-EXEMPT (app/api/v1/exports.py docstring): the body is the raw
    # archive, not {"data": ...} — asserted directly, not via _envelope.
    exp = client.get("/api/v1/exports/clan?format=json", headers=hdr)
    assert exp.status_code == 200, exp.text
    assert "attachment" in exp.headers.get("content-disposition", "")
    archive = json.loads(exp.content)
    # Key names per app/services/clan_export.py's build_clan_export (injected into
    # app/application/export/handlers.py) — verified: "persons", "marriages",
    # "parent_child" match verbatim.
    exported_person_ids = {p["id"] for p in archive["persons"]}
    # Exact equality: a foreign person leaking into this fresh clan's archive
    # (the export walks its own ExportQueryPort path) must fail here.
    assert exported_person_ids == {ong["id"], ba["id"], con["id"]}
    assert len(archive["marriages"]) == 1
    # Raw table rows (SqlAlchemyExportQueryPort.marriages: SELECT * FROM
    # marriages) — column names verified against app/models/marriage.py:
    # person1_id/person2_id, UUIDs stringified by to_json_bytes' default=str.
    mar_row = archive["marriages"][0]
    assert {mar_row["person1_id"], mar_row["person2_id"]} == {ong["id"], ba["id"]}
    assert len(archive["parent_child"]) == 2
    # Same raw-row shape; app/models/parent_child.py: parent_id/child_id.
    pc_pairs = {(row["parent_id"], row["child_id"]) for row in archive["parent_child"]}
    assert pc_pairs == {(ong["id"], con["id"]), (ba["id"], con["id"])}


def test_journey_multiuser_collaboration(
    client: TestClient, stub_identity: StubIdentityProvider, rsa_keys: dict[str, Any]
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
    _envelope(ok, has_meta=True)
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
    # This freshly-created clan has exactly one pending membership (the invitee
    # above was approved immediately in Stage 2), so the joiner is identified by
    # clan-scoped uniqueness. The pending row also carries display_name/email now
    # (PendingClanUserSummary, ADR-039) — pinned in
    # test_clan_users_identity_fields.py, not re-asserted here.
    assert len(pending) == 1, pending
    joiner_row = pending[0]
    assert "person_id" in joiner_row  # ADR-024: key present (null is fine)
    approved = client.post(
        f"/api/v1/clans/me/users/{joiner_row['user_id']}/approve", headers=admin_hdr
    )
    assert approved.status_code == 200, approved.text
    _envelope(approved)
    members = _envelope(client.get("/api/v1/clans/me/users", headers=admin_hdr), has_meta=True)
    # ClanUserSummary also carries no `is_approved` — GET /me/users itself is the
    # approved signal (list_users(clan_id, approved=True, ...) filters server-side
    # in app/api/v1/clans.py::list_clan_users), so membership in this list already
    # means approved; match by the user_id captured from the pending row above.
    assert any(u["user_id"] == joiner_row["user_id"] for u in members)

    # Stage 5 — cross-clan isolation: a foreign X-Current-Clan-Id is rejected by
    # the membership check (same code path whether or not that clan exists).
    # Revisit trigger: if get_current_clan_id ever checks clan existence BEFORE
    # membership, this random-uuid probe stops covering the real foreign-clan
    # case — switch to a genuinely existing foreign clan then.
    foreign = client.get("/api/v1/persons", headers=_auth(viewer_token, str(uuid.uuid4())))
    assert foreign.status_code == 403, foreign.text
    assert _error_code(foreign) == "clan_membership_required"


def test_tree_renders_after_founder_designation(
    client: TestClient, stub_identity: StubIdentityProvider
) -> None:
    """H3 CLOSED by PR A3; the undesignated-clan 404 remains correct and is
    pinned separately (test_tree_404_without_founder_designation).

    Was test_tree_unreachable_for_api_managed_clan_KNOWN_DEFECT_H3, which
    pinned review finding H3 (docs/architecture/backend-review-2026-07-18.md):
    no API path could set is_founder, so find_clan_founder found nothing and
    GET /tree 404d for EVERY clan built through the API. ADR-026's
    `PUT /clans/me/founder` (admin-only) now designates the thủy tổ, and
    GET /tree anchors đời off it — thủy tổ đời 1, per
    docs/architecture/tree-read-model.md."""
    suffix = uuid.uuid4().hex[:10]
    email = f"j3-{suffix}@ex.com"
    _register_create(client, email, f"j3-{suffix}", "Chủ Tộc")
    token, user = _login(client, email)
    clan_id = user["clan_id"]
    hdr = _auth(token, clan_id)
    person = _create_person(client, hdr, "Nguyễn Văn Nhất", "male")

    designation = _envelope(
        client.put(
            "/api/v1/clans/me/founder",
            headers=hdr,
            json={"person_id": person["id"]},
        )
    )
    assert designation["person_id"] == person["id"]

    resp = client.get("/api/v1/tree", headers=hdr)
    assert resp.status_code == 200, resp.text
    root = _envelope(resp)["tree"]
    assert root["id"] == person["id"]
    assert root["generation"] == 1


def test_tree_404_without_founder_designation(
    client: TestClient, stub_identity: StubIdentityProvider
) -> None:
    """CORRECT onboarding state, not a defect: a freshly created clan has no
    thủy tổ until an admin designates one via `PUT /clans/me/founder` — đời is
    graph-computed as distance-from-founder + 1 (docs/architecture/
    tree-read-model.md), so with no founder there is nothing to anchor
    distance from and GET /tree 404s `clan_founder_not_found`. The client flow
    is designate → tree renders (see docs/contracts/
    frontend-integration-guide.md, added by Task 4)."""
    suffix = uuid.uuid4().hex[:10]
    email = f"j3b-{suffix}@ex.com"
    _register_create(client, email, f"j3b-{suffix}", "Chủ Tộc")
    token, user = _login(client, email)
    hdr = _auth(token, user["clan_id"])
    _create_person(client, hdr, "Nguyễn Văn Nhì", "male")

    resp = client.get("/api/v1/tree", headers=hdr)
    assert resp.status_code == 404, resp.text
    assert _error_code(resp) == "clan_founder_not_found"


def test_malformed_cursor_returns_400_invalid_cursor(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    """M9 CLOSED (was test_..._KNOWN_DEFECT_M9): a garbage ?cursor= now returns a
    clean 400 `invalid_cursor` instead of a raw 500 — decode_fields_cursor +
    the person-repo extraction raise AppError(400) (fix/cursor-400). Needs an
    approved clan membership to reach pagination, but
    must not spend this module's auth-prefix budget — a JWT is minted for a
    brand-new uuid user and the profile/clan/approved-membership rows are
    seeded directly via a sync engine (same seeding style as
    tests/integration/test_deactivation_invariant.py), never touching
    /api/v1/auth or /api/v1/invitations.

    Uses a LOCAL TestClient(raise_server_exceptions=False) wrapping the same
    app instance instead of the shared module `client` fixture: the real
    app's BaseHTTPMiddleware stack (Language/RequestMeta/RateLimit) does not
    reliably let httpx's default TestClient observe the registered
    catch-all's JSON response for a genuinely unhandled exception — it
    re-raises into the test process instead (same reasoning documented in
    tests/unit/api/test_persons_batch_endpoint.py's `_build_client`). This
    mirrors real production behavior (the catch-all still returns the 500
    envelope to real clients); it only affects how *this test* observes it."""
    user_id = uuid.uuid4()
    clan_id = uuid.uuid4()
    email = f"m9-{user_id.hex[:8]}@ex.com"
    eng = sa.create_engine(migrated_db_url.replace("+asyncpg", ""))
    try:
        with eng.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name) VALUES (:u, :e, 'M9')"
                ),
                {"u": user_id, "e": email},
            )
            conn.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:c, 'M9 Clan', :sl)"),
                {"c": clan_id, "sl": f"m9-{clan_id.hex[:8]}"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO user_clan_roles (user_id, clan_id, role, is_approved, "
                    "approved_by, approved_at) VALUES (:u, :c, 'viewer', true, :u, now())"
                ),
                {"u": user_id, "c": clan_id},
            )
    finally:
        eng.dispose()

    token = _mint(rsa_keys["private_pem"], user_id, email)
    raw_client = TestClient(client.app, raise_server_exceptions=False)
    resp = raw_client.get(
        "/api/v1/persons?cursor=%%%garbage%%%", headers=_auth(token, str(clan_id))
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "invalid_cursor"


def test_error_localization_over_http(client: TestClient, rsa_keys: dict[str, Any]) -> None:
    """Accept-Language drives the REAL LanguageMiddleware: the same error yields
    an English message under `en` and falls back to Vietnamese for an
    unsupported locale (LanguageMiddleware.dispatch: only the first two chars
    of Accept-Language are checked against SUPPORTED_LOCALES, defaulting to
    "vi" — app/middleware/language_middleware.py, app/core/locale.py). Uses an
    unauthenticated 401 (missing_token, from get_current_user) so it spends no
    rate-limit budget and needs no seeding. The exact strings are pinned
    against app/i18n/en.json / vi.json's "error.missing_token" key so a
    catalog rename or a broken t() lookup (which would echo the raw key
    instead) fails loudly here.

    load_translations() is called explicitly because the shared `client`
    fixture builds a bare TestClient(app) (never entered as a context
    manager), so app.main's lifespan — and therefore
    app.services.translator.load_translations() — never runs for this
    module; without it app.services.translator.t() has an empty catalog and
    silently echoes the raw "error.<code>" key for every locale, which would
    make this test pass or fail depending on unrelated test-run order
    (whichever other module's lifespan happened to populate the
    process-global _translations dict first). Calling it directly here is
    test-only, idempotent, and keeps this test deterministic regardless of
    run order — it does not touch app code."""
    from app.services.translator import load_translations

    load_translations()
    r_en = client.get("/api/v1/persons", headers={"Accept-Language": "en"})
    assert r_en.status_code == 401, r_en.text
    assert _error_code(r_en) == "missing_token"
    msg_en = r_en.json()["error"]["message"]

    r_xx = client.get("/api/v1/persons", headers={"Accept-Language": "xx-YY"})
    assert r_xx.status_code == 401, r_xx.text
    assert _error_code(r_xx) == "missing_token"
    msg_xx = r_xx.json()["error"]["message"]

    assert msg_en != msg_xx  # en differs from the vi fallback
    assert msg_en == "Missing authentication token"  # app/i18n/en.json:"error.missing_token"
    assert msg_xx == "Thiếu token xác thực"  # app/i18n/vi.json:"error.missing_token"
