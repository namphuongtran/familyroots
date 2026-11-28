"""A signed-in user deletes their own account: ``DELETE /api/v1/me`` (#333, ADR-079).

Driven over HTTP with REAL RS256 JWTs (the JWKS cache is primed with a test keypair,
the way ``test_deactivation_invariant.py`` does it), so ``get_current_user`` runs for
real. That matters for one reading: after the deletion, the same still-valid access
token must not bring a profile back (``ensure_user_profile`` would lazily re-create one
from the token's email and name if the row were simply gone).

Every assertion reads an outcome: the response, the rows left in the database, the
call the identity provider received, and the audit trail. The identity provider is a
fake that records ``delete_user``.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwk, jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.security as security_module
from app.core.database import get_db, get_system_db
from app.domain.auth.identity_provider import IdentityUnavailableError
from app.infrastructure.dependencies import get_identity_provider
from app.main import create_app

pytestmark = pytest.mark.integration

_KID = "account-delete-test-key"


class _FakeIdentity:
    """Records the provider calls the deletion makes. ``fail_next`` simulates an
    outage on the next ``delete_user``."""

    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.fail_next = False

    async def delete_user(self, user_id: str) -> None:
        if self.fail_next:
            self.fail_next = False
            raise IdentityUnavailableError("provider down")
        self.deleted.append(user_id)


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
    old_cache, old_time = security_module._jwks_cache, security_module._jwks_cache_time
    security_module._jwks_cache = rsa_keys["jwks"]
    security_module._jwks_cache_time = time.monotonic()
    yield
    security_module._jwks_cache, security_module._jwks_cache_time = old_cache, old_time


def _token(rsa_keys: dict[str, Any], user_id: uuid.UUID, email: str) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "iss": f"{security_module.settings.SUPABASE_URL.rstrip('/')}/auth/v1",  # type: ignore[attr-defined]
        "iat": now,
        "exp": now + timedelta(hours=1),
        "user_metadata": {"full_name": "Người Xóa Tàikhoản"},
    }
    return str(
        jwt.encode(claims, rsa_keys["private_pem"], algorithm="RS256", headers={"kid": _KID})
    )


@pytest.fixture()
def identity() -> _FakeIdentity:
    return _FakeIdentity()


@pytest.fixture()
def client(migrated_db_url: str, jwks_cache: None, identity: _FakeIdentity) -> Iterator[TestClient]:
    app = create_app()
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_db() -> Any:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_system_db] = _override_db
    app.dependency_overrides[get_identity_provider] = lambda: identity
    # Not entered as a context manager, so the lifespan (boot gate, scheduler) stays
    # out of the test, as in test_deactivation_invariant.py.
    yield TestClient(app)
    engine.sync_engine.dispose()


@pytest.fixture()
def db(migrated_db_url: str) -> Iterator[sa.Engine]:
    eng = sa.create_engine(migrated_db_url.replace("+asyncpg", ""))
    yield eng
    eng.dispose()


def _seed(db: sa.Engine) -> dict[str, Any]:
    """The leaving user ``me``: admin of clan A beside a second admin, viewer of clan B,
    linked to a person in clan A, with a pending claim and a push token. A third user,
    ``other_admin``, stays and must be untouched. Clan C has ``solo`` as its only admin."""
    ids: dict[str, Any] = {
        k: uuid.uuid4() for k in ("me", "other_admin", "solo", "a", "b", "c", "person")
    }
    ids["email"] = f"leaving-{ids['me'].hex[:8]}@example.com"
    with db.begin() as c:
        for key in ("a", "b", "c"):
            c.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Họ X', :s)"),
                {"id": ids[key], "s": f"x333-{ids[key].hex[:10]}"},
            )
        c.execute(
            sa.text(
                "INSERT INTO persons (id, full_name, created_by_clan_id, created_by) "
                "VALUES (:id, 'Người Trong Cây', :c, :u)"
            ),
            {"id": ids["person"], "c": ids["a"], "u": ids["other_admin"]},
        )
        c.execute(
            sa.text("INSERT INTO clan_memberships (person_id, clan_id) VALUES (:p, :c)"),
            {"p": ids["person"], "c": ids["a"]},
        )
        for key, email, name, person in (
            ("me", ids["email"], "Người Xóa Tàikhoản", ids["person"]),
            ("other_admin", f"other-{ids['other_admin'].hex[:8]}@example.com", "Khác", None),
            ("solo", f"solo-{ids['solo'].hex[:8]}@example.com", "Một Mình", None),
        ):
            c.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name, avatar_url, person_id)"
                    " VALUES (:id, :e, :n, 'https://cdn.example.com/me.jpg', :p)"
                ),
                {"id": ids[key], "e": email, "n": name, "p": person},
            )
        for user, clan, role in (
            ("me", "a", "admin"),
            ("other_admin", "a", "admin"),
            ("me", "b", "viewer"),
            ("solo", "c", "admin"),
        ):
            c.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:u, :c, :r, true, :u, now())"
                ),
                {"u": ids[user], "c": ids[clan], "r": role},
            )
        c.execute(
            sa.text(
                "INSERT INTO identity_claims (user_id, person_id, status) "
                "VALUES (:u, :p, 'PENDING')"
            ),
            {"u": ids["me"], "p": ids["person"]},
        )
        c.execute(
            sa.text(
                "INSERT INTO user_fcm_tokens (user_id, token, device_platform) "
                "VALUES (:u, :t, 'android')"
            ),
            {"u": ids["me"], "t": f"tok-{ids['me'].hex}"},
        )
    return ids


def _count(db: sa.Engine, sql: str, **params: Any) -> int:
    with db.connect() as c:
        return int(c.execute(sa.text(sql), params).scalar_one())


def test_deleting_my_account_removes_it_everywhere(
    client: TestClient, db: sa.Engine, identity: _FakeIdentity, rsa_keys: dict[str, Any]
) -> None:
    ids = _seed(db)
    me = ids["me"]
    token = _token(rsa_keys, me, ids["email"])

    resp = client.delete("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert "message" in resp.json()["data"]

    # The provider was told to delete exactly this account.
    assert identity.deleted == [str(me)]

    # Memberships and roles in both clans, the claim and the push token are gone.
    assert _count(db, "SELECT count(*) FROM user_clan_roles WHERE user_id = :u", u=me) == 0
    assert _count(db, "SELECT count(*) FROM identity_claims WHERE user_id = :u", u=me) == 0
    assert _count(db, "SELECT count(*) FROM user_fcm_tokens WHERE user_id = :u", u=me) == 0

    # No personal profile data survives: the email, name, avatar and person link.
    with db.connect() as c:
        row = c.execute(
            sa.text("SELECT row_to_json(p)::text FROM user_profiles p WHERE id = :u"), {"u": me}
        ).scalar_one_or_none()
    if row is not None:
        assert ids["email"] not in row
        assert "Tàikhoản" not in row
        assert "me.jpg" not in row
        assert str(ids["person"]) not in row

    # The tree is clan data: the person the account was linked to is still there.
    assert (
        _count(db, "SELECT count(*) FROM persons WHERE id = :p AND NOT is_deleted", p=ids["person"])
        == 1
    )
    # Another member of clan A is untouched.
    assert (
        _count(db, "SELECT count(*) FROM user_clan_roles WHERE user_id = :u", u=ids["other_admin"])
        == 1
    )

    # Audit: one row per clan left (so each clan's trail shows the departure) and
    # one platform row with no clan. None of them carries the email.
    with db.connect() as c:
        audit = c.execute(
            sa.text(
                "SELECT clan_id, actor_id, coalesce(new_value::text, '') AS nv "
                "FROM audit_logs WHERE action = 'account.delete' AND resource_id = :u"
            ),
            {"u": me},
        ).all()
    assert {r.clan_id for r in audit} == {ids["a"], ids["b"], None}
    assert {r.actor_id for r in audit} == {me}
    assert not [r for r in audit if ids["email"] in r.nv]


def test_the_leftover_token_cannot_bring_the_profile_back(
    client: TestClient, db: sa.Engine, rsa_keys: dict[str, Any]
) -> None:
    """The provider's access token stays valid until it expires. After deletion it
    must be refused, and must not re-create a profile carrying the email."""
    ids = _seed(db)
    token = _token(rsa_keys, ids["me"], ids["email"])
    headers = {"Authorization": f"Bearer {token}"}
    assert client.delete("/api/v1/me", headers=headers).status_code == 200

    again = client.get("/api/v1/auth/me", headers=headers)
    assert again.status_code == 403, again.text
    assert again.json()["error"]["code"] == "account_deactivated"
    assert _count(db, "SELECT count(*) FROM user_profiles WHERE email = :e", e=ids["email"]) == 0


def test_the_last_admin_of_a_clan_is_refused_and_nothing_changes(
    client: TestClient, db: sa.Engine, identity: _FakeIdentity, rsa_keys: dict[str, Any]
) -> None:
    ids = _seed(db)
    solo = ids["solo"]
    with db.connect() as c:
        solo_email = c.execute(
            sa.text("SELECT email FROM user_profiles WHERE id = :u"), {"u": solo}
        ).scalar_one()
    token = _token(rsa_keys, solo, solo_email)

    resp = client.delete("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403, resp.text
    error = resp.json()["error"]
    assert error["code"] == "account.last_admin_transfer_first"
    assert error["detail"]["clan_ids"] == [str(ids["c"])]

    assert identity.deleted == []
    assert _count(db, "SELECT count(*) FROM user_clan_roles WHERE user_id = :u", u=solo) == 1
    assert (
        _count(
            db,
            "SELECT count(*) FROM user_profiles WHERE id = :u AND email = :e AND is_active",
            u=solo,
            e=solo_email,
        )
        == 1
    )
    assert (
        _count(
            db,
            "SELECT count(*) FROM audit_logs WHERE action = 'account.delete' AND resource_id = :u",
            u=solo,
        )
        == 0
    )


def test_a_provider_outage_can_be_retried_to_completion(
    client: TestClient, db: sa.Engine, identity: _FakeIdentity, rsa_keys: dict[str, Any]
) -> None:
    """The database step commits before the provider call (ADR-028), so an outage
    leaves a scrubbed, deactivated account. The same request again must finish."""
    ids = _seed(db)
    headers = {"Authorization": f"Bearer {_token(rsa_keys, ids['me'], ids['email'])}"}

    identity.fail_next = True
    first = client.delete("/api/v1/me", headers=headers)
    assert first.status_code == 503, first.text
    assert identity.deleted == []
    assert _count(db, "SELECT count(*) FROM user_clan_roles WHERE user_id = :u", u=ids["me"]) == 0

    second = client.delete("/api/v1/me", headers=headers)
    assert second.status_code == 200, second.text
    assert identity.deleted == [str(ids["me"])]
