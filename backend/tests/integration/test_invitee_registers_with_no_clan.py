"""The invitation flow, walked end to end by a person who has no account (S-085).

ADR-057 findings 1 and 2 together said this flow had never been usable by a new
person: `POST /invitations/{token}/accept` requires an authenticated caller
(`app/api/v1/invitations.py:95-99`), and registration required a `clan_action`,
which an invitee cannot supply -- they have no clan code to type and no clan to
found. ADR-058 makes `clan_action` optional on `POST /auth/register` only.

**What this module asserts, and why it is written this way.** Every test here
sends real HTTP requests and reads real response bodies or real database rows.
None of them asks whether `clan_action` has a default, because that is the
setting the code sets, not the outcome it exists to produce -- see
`.claude/rules/seeds.md`, "A test pins an outcome, not a setting". The walk is
the point: register with no clan, sign in with the token that register made
possible, accept with that token, and read the membership row that lands.

JWT verification is REAL (a test keypair is injected into the JWKS cache, the
pattern `test_e2e_journeys.py` established); the identity provider is the only
stubbed seam. So the Bearer token the accept step uses is the very token
`POST /auth/login` returned for the clanless account -- which is the property
that matters, because ADR-048 kept accept behind `get_current_user` and behind
the invitation's email-match rule.

**Session wiring.** ADR-048 put accept on the privileged system session, so
`get_system_db` is overridden as well as `get_db`. Overriding only `get_db`
would reach the real engine.

**Rate-limit budget.** `RateLimitMiddleware` holds `_hits` per instance
(`app/core/rate_limit.py:52`), and the `client` fixture below is
function-scoped, so each test gets its own app and its own 20 req/min/IP
bucket. The walk spends 7 on the `/api/v1/auth` + `/api/v1/invitations`
prefixes; `POST /api/v1/clans/{clan_id}/invitations` matches neither prefix and
is free. Re-count before adding requests.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator, Iterator
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

_KID = "s085-invitee-key"
_PW = "Str0ng!pass-s085"


# ── the identity seam ────────────────────────────────────────────────────────


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
    return f"{security_module.settings.SUPABASE_URL.rstrip('/')}/auth/v1"  # type: ignore[attr-defined]


class StubIdentityProvider:
    """In-memory IdentityProvider that mints verifiable RS256 JWTs.

    ``create_user`` records **no** name, exactly as the real port cannot carry
    one: ``IdentityProvider.create_user`` takes ``email`` and ``password`` only
    (``app/domain/auth/identity_provider.py:75``). That is why the name a person
    types at registration has to be written locally, and why
    ``test_the_name_typed_at_register_survives_accept`` is a real assertion and
    not a tautology.
    """

    def __init__(self, private_pem: str) -> None:
        self._private_pem = private_pem
        self._users: dict[str, dict[str, str]] = {}
        self.verification_emails: list[str] = []
        self.password_resets: list[str] = []
        self.create_user_calls: list[str] = []

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
        self.create_user_calls.append(email)
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
        raise IdentityAuthError("not used here")

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


@pytest.fixture()
def stub_identity(rsa_keys: dict[str, Any]) -> StubIdentityProvider:
    return StubIdentityProvider(rsa_keys["private_pem"])


@pytest.fixture()
def client(
    migrated_db_url: str, stub_identity: StubIdentityProvider, jwks_cache: None
) -> Iterator[TestClient]:
    app = create_app()
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    # ADR-048: accept runs on the privileged system session.
    app.dependency_overrides[get_system_db] = _override_db
    app.dependency_overrides[get_identity_provider] = lambda: stub_identity
    yield TestClient(app)
    engine.sync_engine.dispose()


@pytest.fixture()
async def db_session(migrated_db_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


# ── helpers ──────────────────────────────────────────────────────────────────


def _data(resp: Any) -> Any:
    body = resp.json()
    assert set(body.keys()) == {"data"}, body
    return body["data"]


def _error_code(resp: Any) -> str:
    body = resp.json()
    assert set(body.keys()) == {"error"}, body
    assert set(body["error"].keys()) == {"code", "message", "detail"}, body
    return cast(str, body["error"]["code"])


def _auth(token: str, clan_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if clan_id:
        headers["X-Current-Clan-Id"] = clan_id
    return headers


def _found_clan(client: TestClient, suffix: str, tag: str) -> tuple[str, str]:
    """Register a founding admin, sign them in, and return (clan_id, token)."""
    email = f"{tag}-{suffix}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": _PW,
            "full_name": f"Truong Toc {tag}",
            "clan_action": "create",
            "clan_name": f"Ho {tag} {suffix}",
            "clan_slug": f"{tag}-{suffix}",
        },
    )
    assert resp.status_code == 201, resp.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": _PW})
    assert login.status_code == 200, login.text
    data = _data(login)
    return cast(str, data["user"]["clan_id"]), cast(str, data["access_token"])


def _invite(client: TestClient, admin_hdr: dict[str, str], clan_id: str, email: str) -> str:
    """Admin invites ``email`` as a viewer; returns the raw token."""
    resp = client.post(
        f"/api/v1/clans/{clan_id}/invitations",
        headers=admin_hdr,
        json={"email": email, "role": "viewer"},
    )
    assert resp.status_code == 201, resp.text
    return cast(str, _data(resp)["token"])


_CLANLESS_NAME = "Nguoi Duoc Moi"


def _clanless_register_body(email: str) -> dict[str, Any]:
    """The invitee's register body: no ``clan_action`` and no clan field at all."""
    return {"email": email, "password": _PW, "full_name": _CLANLESS_NAME}


# ── the walk ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_invitee_with_no_account_completes_the_whole_flow(
    client: TestClient,
    stub_identity: StubIdentityProvider,
    db_session: AsyncSession,
) -> None:
    """Register with no clan, sign in, accept -- and read the membership row.

    This is the end state seed S-085 names. Every stage reads a response body or
    a database row. Against the code before ADR-058, Stage 3 is where it stops.
    """
    suffix = uuid.uuid4().hex[:10]
    invitee_email = f"invitee-{suffix}@example.com"

    # Stage 1 -- two clans exist. Clan B is the other side of the isolation read
    # in Stage 6: it must never see this membership.
    clan_a, admin_a_token = _found_clan(client, suffix, "a")
    clan_b, _ = _found_clan(client, suffix, "b")
    assert clan_a != clan_b

    # Stage 2 -- clan A's admin invites the stranger by email.
    token = _invite(client, _auth(admin_a_token, clan_a), clan_a, invitee_email)
    assert token

    # Stage 3 -- the stranger registers. No clan_action, no clan field.
    # THIS is the step ADR-057 finding 2 made impossible.
    reg = client.post("/api/v1/auth/register", json=_clanless_register_body(invitee_email))
    assert reg.status_code == 201, reg.text
    # The non-enumerating envelope is unchanged: a bare message, no ids.
    assert set(_data(reg).keys()) == {"message"}
    # Registration still ends in a verification email, clanless or not.
    assert stub_identity.verification_emails.count(invitee_email) == 1

    # Stage 4 -- verify, then sign in. Verification itself is out of scope
    # (seed S-085); the stub models an account whose email is confirmed. What is
    # asserted here is the profile a clanless account presents: no clan, not
    # approved, and nothing pending.
    login = client.post("/api/v1/auth/login", json={"email": invitee_email, "password": _PW})
    assert login.status_code == 200, login.text
    profile = _data(login)["user"]
    assert profile["clan_id"] is None
    assert profile["is_approved"] is False
    assert profile["has_pending_membership"] is False
    assert profile["role"] is None
    invitee_token = _data(login)["access_token"]

    # Stage 5 -- accept, with the token that sign-in just returned. This is the
    # dependency ADR-057 finding 1 named: accept needs an authenticated caller.
    acc = client.post(f"/api/v1/invitations/{token}/accept", headers=_auth(invitee_token))
    assert acc.status_code == 200, acc.text
    accepted = _data(acc)
    assert accepted["clan_id"] == clan_a
    assert accepted["role"] == "viewer"

    # Stage 6 -- read the database, both sides. Clan A holds the membership and
    # clan B holds nothing, asserted against `user_clan_roles` directly rather
    # than through an API that joins on the caller's clan.
    user_id = uuid.UUID(
        cast(
            str,
            (
                await db_session.execute(
                    sa.text("SELECT id::text FROM user_profiles WHERE email = :e"),
                    {"e": invitee_email},
                )
            ).scalar_one(),
        )
    )
    rows = (
        await db_session.execute(
            sa.text(
                "SELECT clan_id::text, role, is_approved FROM user_clan_roles "
                "WHERE user_id = :u ORDER BY clan_id"
            ),
            {"u": str(user_id)},
        )
    ).all()
    assert [tuple(r) for r in rows] == [(clan_a, "viewer", True)]
    assert (
        await db_session.execute(
            sa.text("SELECT count(*) FROM user_clan_roles WHERE user_id = :u AND clan_id = :c"),
            {"u": str(user_id), "c": clan_b},
        )
    ).scalar_one() == 0

    # Stage 7 -- sign in again: the same account now reports clan A as a viewer.
    # The flow is complete end to end, which is the seed's end state.
    after = client.post("/api/v1/auth/login", json={"email": invitee_email, "password": _PW})
    assert after.status_code == 200, after.text
    after_profile = _data(after)["user"]
    assert after_profile["clan_id"] == clan_a
    assert after_profile["is_approved"] is True
    assert after_profile["role"] == "viewer"


@pytest.mark.asyncio
async def test_the_name_typed_at_register_survives_accept(
    client: TestClient,
    db_session: AsyncSession,
) -> None:
    """`user_profiles.display_name` is the name the person typed, not a fallback.

    Nothing carries a name to the identity provider (`create_user` takes email
    and password only), so the clanless register path is the only writer of this
    person's name. Invitation accept calls `ensure_profile` again with the JWT's
    `user_metadata.full_name`, which is empty for a registered account, and
    `ensure_profile_row` is ON CONFLICT DO NOTHING -- so if register wrote no
    row, this reads the local-part of the email instead of the real name.
    """
    suffix = uuid.uuid4().hex[:10]
    invitee_email = f"named-{suffix}@example.com"
    clan_a, admin_token = _found_clan(client, suffix, "n")
    token = _invite(client, _auth(admin_token, clan_a), clan_a, invitee_email)

    assert (
        client.post(
            "/api/v1/auth/register", json=_clanless_register_body(invitee_email)
        ).status_code
        == 201
    )
    login = client.post("/api/v1/auth/login", json={"email": invitee_email, "password": _PW})
    accept = client.post(
        f"/api/v1/invitations/{token}/accept", headers=_auth(_data(login)["access_token"])
    )
    assert accept.status_code == 200, accept.text

    display_name = (
        await db_session.execute(
            sa.text("SELECT display_name FROM user_profiles WHERE email = :e"),
            {"e": invitee_email},
        )
    ).scalar_one()
    assert display_name == _CLANLESS_NAME


# ── the non-enumeration property, which does not bend ────────────────────────


def test_clanless_register_is_indistinguishable_for_a_known_and_an_unknown_email(
    client: TestClient, stub_identity: StubIdentityProvider
) -> None:
    """Two runs of the same clanless body: one email registered, one not.

    Spec 7.1b at `docs/superpowers/specs/2026-08-02-design-system-and-screens.md:871-873`
    -- a 201 always routes to the same screen and must never say an account
    exists. The two responses are compared whole, status and body.
    """
    suffix = uuid.uuid4().hex[:10]
    known = f"known-{suffix}@example.com"
    unknown = f"unknown-{suffix}@example.com"

    first = client.post("/api/v1/auth/register", json=_clanless_register_body(known))
    assert first.status_code == 201, first.text

    # Second run: `known` now has an account, `unknown` does not.
    repeat = client.post("/api/v1/auth/register", json=_clanless_register_body(known))
    fresh = client.post("/api/v1/auth/register", json=_clanless_register_body(unknown))

    assert repeat.status_code == fresh.status_code == 201
    assert repeat.json() == fresh.json()

    # The registered email was not created twice and got the silent nudge
    # instead (ADR-021); the fresh one was created. Neither difference reaches
    # the caller.
    assert stub_identity.create_user_calls == [known, unknown]
    assert stub_identity.password_resets == [known]


@pytest.mark.asyncio
async def test_a_repeat_clanless_register_writes_no_second_profile(
    client: TestClient, db_session: AsyncSession
) -> None:
    """The existing-email branch returns before any database write.

    Read as a row count rather than as a response, because the response is
    required to be identical either way -- so the response cannot be the
    evidence for this.
    """
    suffix = uuid.uuid4().hex[:10]
    email = f"repeat-{suffix}@example.com"
    assert (
        client.post("/api/v1/auth/register", json=_clanless_register_body(email)).status_code == 201
    )
    before = (await db_session.execute(sa.text("SELECT count(*) FROM user_profiles"))).scalar_one()

    assert (
        client.post("/api/v1/auth/register", json=_clanless_register_body(email)).status_code == 201
    )
    after = (await db_session.execute(sa.text("SELECT count(*) FROM user_profiles"))).scalar_one()
    assert after == before


def test_a_body_that_names_a_clan_without_an_action_is_refused_identically(
    client: TestClient, stub_identity: StubIdentityProvider
) -> None:
    """`clan_code` with no `clan_action` is a 422 `validation_error`, both paths.

    The refusal happens in `RegisterRequest`, before the route body runs, so the
    identity provider is never consulted -- which is what makes it impossible
    for this branch to answer differently for a registered and an unregistered
    email. No new error code is added to this route.
    """
    suffix = uuid.uuid4().hex[:10]
    known = f"k2-{suffix}@example.com"
    assert (
        client.post("/api/v1/auth/register", json=_clanless_register_body(known)).status_code == 201
    )
    stub_identity.create_user_calls.clear()
    stub_identity.password_resets.clear()

    body = {**_clanless_register_body(known), "clan_code": f"some-clan-{suffix}"}
    on_known = client.post("/api/v1/auth/register", json=body)
    on_unknown = client.post(
        "/api/v1/auth/register",
        json={**body, "email": f"u2-{suffix}@example.com"},
    )

    assert on_known.status_code == on_unknown.status_code == 422
    assert on_known.json() == on_unknown.json()
    assert _error_code(on_known) == "validation_error"
    # The contract states this reading (docs/contracts/rest-auth-api.md,
    # "Registering with no clan"): the refusal is model-level, so `loc` is the
    # whole body rather than one field.
    assert on_known.json()["error"]["detail"] == {"fields": ["body"]}
    assert stub_identity.create_user_calls == []
    assert stub_identity.password_resets == []


def test_join_with_no_identifier_still_answers_clan_id_required_for_join(
    client: TestClient,
) -> None:
    """`clan_action=join` with neither identifier is unchanged by ADR-058.

    This is the reading the seed's negative control expects, and the code spec
    7.1b writes the register form's field-level error handling around. Making
    `clan_action` optional must not turn an explicit join with a missing code
    into a silent clanless account.
    """
    suffix = uuid.uuid4().hex[:10]
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"j-{suffix}@example.com",
            "password": _PW,
            "full_name": "Nguoi Xin Gia Nhap",
            "clan_action": "join",
        },
    )
    assert resp.status_code == 422, resp.text
    assert _error_code(resp) == "auth.clan_id_required_for_join"
