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
/api/v1/auth + /api/v1/invitations — matched by path PREFIX, so GET /auth/me
counts too. Current spend: J1=3 auth (register, login, /auth/me), J2=3 auth + 2
invitations, J3=2 auth → 10/20. Re-count before adding requests on those prefixes.
"""

import json
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwk, jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.security as security_module
from app.core.database import get_db
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
    ancestor_ids = {
        a["id"] for a in _envelope(client.get(f"/api/v1/tree/ancestors/{con['id']}", headers=hdr))
    }
    assert {ong["id"], ba["id"]} <= ancestor_ids

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
    assert {ong["id"], ba["id"], con["id"]} <= exported_person_ids
    assert len(archive["marriages"]) == 1
    assert len(archive["parent_child"]) == 2
