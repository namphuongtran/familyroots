"""H3 (review 2026-07-18): the thủy tổ (clan founder) was unsettable through the
API — no route ever set ``clan_memberships.is_founder``, so ``GET /tree`` 404s for
every API-managed clan (đời is graph-computed from founder distance + 1; no
founder means no root to compute distance from). ADR-026 adds
``PUT /clans/me/founder`` to designate or correct the founder.

Reuses the RS256/JWKS/client harness from ``test_deactivation_invariant.py`` (the
leanest instance): real RS256 JWTs verified against a primed JWKS cache, client
overrides ONLY ``get_db``. RBAC and audit logging run for real over a migrated
Postgres.
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
from app.core.database import get_db
from app.main import create_app

pytestmark = pytest.mark.integration

_KID = "founder-test-key"


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


def _issuer() -> str:
    return f"{security_module.settings.SUPABASE_URL.rstrip('/')}/auth/v1"  # type: ignore[attr-defined]


def _mint(private_pem: str, user_id: uuid.UUID, email: str) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "iss": _issuer(),
        "iat": now,
        "exp": now + timedelta(hours=1),
        "user_metadata": {"full_name": "Founder Test"},
    }
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": _KID})


@pytest.fixture(scope="module")
def client(migrated_db_url: str, jwks_cache: None) -> Iterator[TestClient]:
    app = create_app()
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    yield TestClient(app)
    engine.sync_engine.dispose()


def _sync_engine(dsn: str) -> sa.Engine:
    return sa.create_engine(dsn.replace("+asyncpg", ""))


# ── Seeding helpers ──────────────────────────────────────────────────────────


def _seed_clan(conn: sa.Connection, *, name: str = "C") -> uuid.UUID:
    clan_id = uuid.uuid4()
    conn.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:c, :n, :sl)"),
        {"c": clan_id, "n": name, "sl": f"c-{clan_id.hex[:8]}"},
    )
    return clan_id


def _seed_user_with_role(
    conn: sa.Connection, clan_id: uuid.UUID, *, role: str, approved: bool = True
) -> tuple[uuid.UUID, str]:
    """user_profiles row + a user_clan_roles row for `clan_id`; returns (user_id, email)."""
    user_id = uuid.uuid4()
    email = f"founder-{user_id.hex[:8]}@ex.com"
    conn.execute(
        sa.text(
            "INSERT INTO user_profiles (id, email, display_name, is_active) "
            "VALUES (:u, :e, 'U', true)"
        ),
        {"u": user_id, "e": email},
    )
    conn.execute(
        sa.text(
            "INSERT INTO user_clan_roles (user_id, clan_id, role, is_approved, "
            "approved_by, approved_at) VALUES (:u, :c, :r, :ap, :u, now())"
        ),
        {"u": user_id, "c": clan_id, "r": role, "ap": approved},
    )
    return user_id, email


def _seed_person(
    conn: sa.Connection, clan_id: uuid.UUID, *, name: str = "P", is_deleted: bool = False
) -> uuid.UUID:
    """A live (or soft-deleted) person, plus a ``clan_memberships`` row for `clan_id`."""
    person_id = uuid.uuid4()
    creator = uuid.uuid4()
    conn.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, created_by_clan_id, created_by, is_deleted) "
            "VALUES (:id, :n, :c, :cb, :del)"
        ),
        {"id": person_id, "n": name, "c": clan_id, "cb": creator, "del": is_deleted},
    )
    conn.execute(
        sa.text(
            "INSERT INTO clan_memberships (id, person_id, clan_id, role) "
            "VALUES (:id, :p, :c, 'blood')"
        ),
        {"id": uuid.uuid4(), "p": person_id, "c": clan_id},
    )
    return person_id


def _seed_parent_child(
    conn: sa.Connection, parent_id: uuid.UUID, child_id: uuid.UUID, clan_id: uuid.UUID
) -> None:
    """A live biological parent_child edge (same shape as tests/integration/test_tree_focus.py)."""
    creator = uuid.uuid4()
    conn.execute(
        sa.text(
            "INSERT INTO parent_child "
            "(id, parent_id, child_id, created_by_clan_id, relationship_type, created_by) "
            "VALUES (:id, :p, :c, :cl, 'biological', :cb)"
        ),
        {"id": uuid.uuid4(), "p": parent_id, "c": child_id, "cl": clan_id, "cb": creator},
    )


def _founder_person_ids(conn: sa.Connection, clan_id: uuid.UUID) -> list[uuid.UUID]:
    rows = conn.execute(
        sa.text("SELECT person_id FROM clan_memberships WHERE clan_id = :c AND is_founder = true"),
        {"c": clan_id},
    ).all()
    return [r[0] for r in rows]


def _audit_row(conn: sa.Connection, clan_id: uuid.UUID) -> sa.engine.Row[Any] | None:
    return conn.execute(
        sa.text(
            "SELECT action, clan_id, actor_id, resource_type FROM audit_logs "
            "WHERE clan_id = :c AND action = 'clan.founder_designate' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"c": clan_id},
    ).first()


def _designate(client: TestClient, token: str, clan_id: uuid.UUID, person_id: uuid.UUID) -> Any:
    return client.put(
        "/api/v1/clans/me/founder",
        headers={"Authorization": f"Bearer {token}", "X-Current-Clan-Id": str(clan_id)},
        json={"person_id": str(person_id)},
    )


# ── Tests ────────────────────────────────────────────────────────────────────


def test_designate_founder_succeeds_and_audits(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    eng = _sync_engine(migrated_db_url)
    try:
        with eng.begin() as conn:
            clan_id = _seed_clan(conn)
            admin_id, admin_email = _seed_user_with_role(conn, clan_id, role="admin")
            person_a = _seed_person(conn, clan_id, name="A")

        admin_token = _mint(rsa_keys["private_pem"], admin_id, admin_email)
        resp = _designate(client, admin_token, clan_id, person_a)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["person_id"] == str(person_a)
        assert data["previous_person_id"] is None
        assert data["message"]  # localized, non-empty

        # schema<->body coherence (documentation-only responses= must not drift)
        from app.schemas.clan import FounderDesignationResponse

        FounderDesignationResponse.model_validate(data)

        with eng.connect() as conn:
            founders = _founder_person_ids(conn, clan_id)
            assert founders == [person_a]

            audit = _audit_row(conn, clan_id)
            assert audit is not None, "expected a clan.founder_designate audit_logs row"
            assert audit.action == "clan.founder_designate"
            assert audit.clan_id == clan_id
            assert audit.actor_id == admin_id
            assert audit.resource_type == "clan_membership"
    finally:
        eng.dispose()


def test_correction_swaps_and_reports_previous(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    eng = _sync_engine(migrated_db_url)
    try:
        with eng.begin() as conn:
            clan_id = _seed_clan(conn)
            admin_id, admin_email = _seed_user_with_role(conn, clan_id, role="admin")
            person_a = _seed_person(conn, clan_id, name="A")
            person_b = _seed_person(conn, clan_id, name="B")

        admin_token = _mint(rsa_keys["private_pem"], admin_id, admin_email)
        resp_a = _designate(client, admin_token, clan_id, person_a)
        assert resp_a.status_code == 200, resp_a.text

        resp_b = _designate(client, admin_token, clan_id, person_b)
        assert resp_b.status_code == 200, resp_b.text
        data_b = resp_b.json()["data"]
        assert data_b["person_id"] == str(person_b)
        assert data_b["previous_person_id"] == str(person_a)

        with eng.connect() as conn:
            founders = _founder_person_ids(conn, clan_id)
            assert founders == [person_b]
    finally:
        eng.dispose()


def test_idempotent_redesignation(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    eng = _sync_engine(migrated_db_url)
    try:
        with eng.begin() as conn:
            clan_id = _seed_clan(conn)
            admin_id, admin_email = _seed_user_with_role(conn, clan_id, role="admin")
            person_a = _seed_person(conn, clan_id, name="A")

        admin_token = _mint(rsa_keys["private_pem"], admin_id, admin_email)
        first = _designate(client, admin_token, clan_id, person_a)
        assert first.status_code == 200, first.text

        second = _designate(client, admin_token, clan_id, person_a)
        assert second.status_code == 200, second.text
        data = second.json()["data"]
        assert data["person_id"] == str(person_a)
        assert data["previous_person_id"] == str(person_a)

        with eng.connect() as conn:
            founders = _founder_person_ids(conn, clan_id)
            assert founders == [person_a]  # still exactly one founder row

            # The idempotent re-designation still writes its own audit row —
            # idempotent means "no founder-state change", not "no audit trail".
            audit_count = conn.execute(
                sa.text(
                    "SELECT COUNT(*) FROM audit_logs "
                    "WHERE clan_id = :c AND action = 'clan.founder_designate'"
                ),
                {"c": clan_id},
            ).scalar_one()
            assert audit_count == 2
    finally:
        eng.dispose()


def test_foreign_clan_person_404_two_sided(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    eng = _sync_engine(migrated_db_url)
    try:
        with eng.begin() as conn:
            clan_id = _seed_clan(conn, name="Clan A")
            admin_id, admin_email = _seed_user_with_role(conn, clan_id, role="admin")

            other_clan_id = _seed_clan(conn, name="Clan B")
            foreign_person = _seed_person(conn, other_clan_id, name="Foreign")

        admin_token = _mint(rsa_keys["private_pem"], admin_id, admin_email)
        resp = _designate(client, admin_token, clan_id, foreign_person)
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "person_not_found"

        # The foreign clan's own data must be untouched.
        with eng.connect() as conn:
            assert _founder_person_ids(conn, clan_id) == []
            assert _founder_person_ids(conn, other_clan_id) == []
    finally:
        eng.dispose()


def test_soft_deleted_person_404(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    eng = _sync_engine(migrated_db_url)
    try:
        with eng.begin() as conn:
            clan_id = _seed_clan(conn)
            admin_id, admin_email = _seed_user_with_role(conn, clan_id, role="admin")
            deleted_person = _seed_person(conn, clan_id, name="Deleted", is_deleted=True)

        admin_token = _mint(rsa_keys["private_pem"], admin_id, admin_email)
        resp = _designate(client, admin_token, clan_id, deleted_person)
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "person_not_found"

        with eng.connect() as conn:
            assert _founder_person_ids(conn, clan_id) == []
    finally:
        eng.dispose()


def test_viewer_and_editor_403(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    eng = _sync_engine(migrated_db_url)
    try:
        with eng.begin() as conn:
            clan_id = _seed_clan(conn)
            viewer_id, viewer_email = _seed_user_with_role(conn, clan_id, role="viewer")
            editor_id, editor_email = _seed_user_with_role(conn, clan_id, role="editor")
            person_a = _seed_person(conn, clan_id, name="A")

        viewer_token = _mint(rsa_keys["private_pem"], viewer_id, viewer_email)
        resp_viewer = _designate(client, viewer_token, clan_id, person_a)
        assert resp_viewer.status_code == 403, resp_viewer.text
        assert resp_viewer.json()["error"]["code"] == "insufficient_permissions"

        editor_token = _mint(rsa_keys["private_pem"], editor_id, editor_email)
        resp_editor = _designate(client, editor_token, clan_id, person_a)
        assert resp_editor.status_code == 403, resp_editor.text
        assert resp_editor.json()["error"]["code"] == "insufficient_permissions"

        with eng.connect() as conn:
            assert _founder_person_ids(conn, clan_id) == []
    finally:
        eng.dispose()


# ── Race (DB-level, raw SQL): enforced by Task 2's unique index ──────────────

_CLEAR_FOUNDER = sa.text(
    "UPDATE clan_memberships SET is_founder = false WHERE clan_id = :c AND is_founder"
)
_SET_FOUNDER = sa.text(
    "UPDATE clan_memberships SET is_founder = true WHERE person_id = :p AND clan_id = :c"
)


async def test_designation_race_never_two_founders(migrated_db_url: str) -> None:
    """Two concurrent transactions each do clear-then-set for different persons.

    Task 2's partial unique index (``uq_clan_memberships_one_founder``) makes
    it impossible for both writers to commit a second live founder row: the
    losing writer either serializes behind the winner (clear-then-set runs
    against the winner's already-committed row and simply re-wins) or its
    UPDATE hits 23505 (unique_violation) and is rejected. The invariant this
    test pins is: afterwards the clan has <= 1 founder row. It must never be
    weakened to tolerate >1.
    """
    import asyncio

    from sqlalchemy.exc import DBAPIError

    engine = create_async_engine(migrated_db_url)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        clan_id = uuid.uuid4()
        person_a, person_b = uuid.uuid4(), uuid.uuid4()
        async with maker() as s:
            await s.execute(
                sa.text("INSERT INTO clans (id, name, slug) VALUES (:c, 'C', :sl)"),
                {"c": clan_id, "sl": f"race-{clan_id.hex[:8]}"},
            )
            for pid, name in ((person_a, "A"), (person_b, "B")):
                creator = uuid.uuid4()
                await s.execute(
                    sa.text(
                        "INSERT INTO persons (id, full_name, created_by_clan_id, created_by) "
                        "VALUES (:id, :n, :c, :cb)"
                    ),
                    {"id": pid, "n": name, "c": clan_id, "cb": creator},
                )
                await s.execute(
                    sa.text(
                        "INSERT INTO clan_memberships (id, person_id, clan_id, role) "
                        "VALUES (:id, :p, :c, 'blood')"
                    ),
                    {"id": uuid.uuid4(), "p": pid, "c": clan_id},
                )
            await s.commit()

        async def _run(person_id: uuid.UUID, gate: asyncio.Event) -> str:
            async with maker() as s:
                await gate.wait()
                try:
                    await s.execute(_CLEAR_FOUNDER, {"c": clan_id})
                    await s.execute(_SET_FOUNDER, {"p": person_id, "c": clan_id})
                    await s.commit()
                    return "ok"
                except DBAPIError:
                    await s.rollback()
                    return "rejected"

        gate = asyncio.Event()
        t1 = asyncio.create_task(_run(person_a, gate))
        t2 = asyncio.create_task(_run(person_b, gate))
        gate.set()
        results = sorted(await asyncio.wait_for(asyncio.gather(t1, t2), timeout=30))
        assert "ok" in results  # at most one WIN is required; the loser may also succeed serially

        async with maker() as s:
            count = await s.scalar(
                sa.text(
                    "SELECT COUNT(*) FROM clan_memberships WHERE clan_id = :c AND is_founder = true"
                ),
                {"c": clan_id},
            )
        assert count is not None and count <= 1, (
            f"expected at most one founder after the race, got {count} "
            "(DB-enforced by uq_clan_memberships_one_founder, migration 023)"
        )
    finally:
        await engine.dispose()


# ── Sabotage (DB-level, raw SQL): 023's index is the last line of defense ────


def test_second_founder_blocked_at_db(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    """023's partial unique index (``uq_clan_memberships_one_founder``) holds
    even when a write bypasses the API and its clear-then-set discipline
    entirely: a raw-SQL UPDATE that flips a second person's membership to
    founder — while the first founder row designated via the API is still
    live — must be rejected at the database, not silently accepted.
    """
    from sqlalchemy.exc import DBAPIError, IntegrityError

    eng = _sync_engine(migrated_db_url)
    try:
        with eng.begin() as conn:
            clan_id = _seed_clan(conn)
            admin_id, admin_email = _seed_user_with_role(conn, clan_id, role="admin")
            person_a = _seed_person(conn, clan_id, name="A")
            person_b = _seed_person(conn, clan_id, name="B")

        admin_token = _mint(rsa_keys["private_pem"], admin_id, admin_email)
        resp = _designate(client, admin_token, clan_id, person_a)
        assert resp.status_code == 200, resp.text

        # Bypass the API entirely: raw SQL sets B's membership to founder
        # while A's founder row (set via the API above) is still live.
        with (
            pytest.raises((DBAPIError, IntegrityError), match="uq_clan_memberships_one_founder"),
            eng.begin() as conn,
        ):
            conn.execute(_SET_FOUNDER, {"p": person_b, "c": clan_id})

        with eng.connect() as conn:
            assert _founder_person_ids(conn, clan_id) == [person_a]
    finally:
        eng.dispose()


# ── Đời proof: designation is what makes generation-anchoring possible ──────


def test_designating_founder_activates_doi_across_three_generations(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    """Seeds founder → child → grandchild (biological parent_child edges, one
    clan) via raw SQL, designates the founder through the API, then asserts
    GET /tree and GET /tree/focus/{grandchild} both anchor đời off the newly
    designated thủy tổ: founder đời 1, child đời 2, grandchild đời 3."""
    eng = _sync_engine(migrated_db_url)
    try:
        with eng.begin() as conn:
            clan_id = _seed_clan(conn)
            admin_id, admin_email = _seed_user_with_role(conn, clan_id, role="admin")
            founder = _seed_person(conn, clan_id, name="Founder")
            child = _seed_person(conn, clan_id, name="Child")
            grandchild = _seed_person(conn, clan_id, name="Grandchild")
            _seed_parent_child(conn, founder, child, clan_id)
            _seed_parent_child(conn, child, grandchild, clan_id)

        admin_token = _mint(rsa_keys["private_pem"], admin_id, admin_email)
        designate_resp = _designate(client, admin_token, clan_id, founder)
        assert designate_resp.status_code == 200, designate_resp.text

        tree_resp = client.get(
            "/api/v1/tree",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Current-Clan-Id": str(clan_id),
            },
        )
        assert tree_resp.status_code == 200, tree_resp.text
        root = tree_resp.json()["data"]["tree"]
        assert root["id"] == str(founder)
        assert root["generation"] == 1
        assert root["is_founder"] is True
        assert len(root["children"]) == 1
        child_node = root["children"][0]
        assert child_node["id"] == str(child)
        assert child_node["generation"] == 2
        assert len(child_node["children"]) == 1
        grandchild_node = child_node["children"][0]
        assert grandchild_node["id"] == str(grandchild)
        assert grandchild_node["generation"] == 3

        focus_resp = client.get(
            f"/api/v1/tree/focus/{grandchild}",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Current-Clan-Id": str(clan_id),
            },
        )
        assert focus_resp.status_code == 200, focus_resp.text
        assert focus_resp.json()["data"]["generation_of_focus"] == 3
    finally:
        eng.dispose()


# ── Restore semantics (final review, live-disproven doc claim) ──────────────


def test_restoring_soft_deleted_founder_reroots_tree(
    client: TestClient, migrated_db_url: str, rsa_keys: dict[str, Any]
) -> None:
    """Ground truth (live-verified): PersonCommandHandler.restore only flips
    persons.is_deleted back to false — it never touches the founder's
    clan_memberships.is_founder flag, and find_clan_founder's only founder
    filter is p.is_deleted = false. So designate A → soft-delete A → GET /tree
    404s (founder unreachable) → restore A via the API alone (no re-designation
    call) → GET /tree 200s rooted at A again, generation 1.

    Both delete and restore go through the real HTTP API (DELETE /persons/{id},
    POST /persons/{id}/restore) rather than raw SQL: both routes are admin-only
    with no expected_version/OCC requirement (DeletePerson/RestorePerson carry
    no expected_version field, unlike PATCH /persons), so there is no OCC
    friction that would justify dropping to raw SQL for either leg — the full
    handler + audit-logging path runs for real, which is exactly what this test
    is pinning.
    """
    eng = _sync_engine(migrated_db_url)
    try:
        with eng.begin() as conn:
            clan_id = _seed_clan(conn)
            admin_id, admin_email = _seed_user_with_role(conn, clan_id, role="admin")
            person_a = _seed_person(conn, clan_id, name="A")

        admin_token = _mint(rsa_keys["private_pem"], admin_id, admin_email)
        hdr = {"Authorization": f"Bearer {admin_token}", "X-Current-Clan-Id": str(clan_id)}

        designate_resp = _designate(client, admin_token, clan_id, person_a)
        assert designate_resp.status_code == 200, designate_resp.text

        tree_before = client.get("/api/v1/tree", headers=hdr)
        assert tree_before.status_code == 200, tree_before.text
        assert tree_before.json()["data"]["tree"]["id"] == str(person_a)

        delete_resp = client.delete(f"/api/v1/persons/{person_a}", headers=hdr)
        assert delete_resp.status_code == 200, delete_resp.text

        tree_while_deleted = client.get("/api/v1/tree", headers=hdr)
        assert tree_while_deleted.status_code == 404, tree_while_deleted.text
        assert tree_while_deleted.json()["error"]["code"] == "clan_founder_not_found"

        # The is_founder flag itself must still be set — restore alone must be
        # what re-roots the tree, not a hidden re-designation.
        with eng.connect() as conn:
            assert _founder_person_ids(conn, clan_id) == [person_a]

        restore_resp = client.post(f"/api/v1/persons/{person_a}/restore", headers=hdr)
        assert restore_resp.status_code == 200, restore_resp.text

        tree_after = client.get("/api/v1/tree", headers=hdr)
        assert tree_after.status_code == 200, tree_after.text
        root = tree_after.json()["data"]["tree"]
        assert root["id"] == str(person_a)
        assert root["generation"] == 1
        assert root["is_founder"] is True

        with eng.connect() as conn:
            # Still exactly one founder row, unchanged since designation —
            # no swap/clear-then-set ever ran during delete or restore.
            assert _founder_person_ids(conn, clan_id) == [person_a]
    finally:
        eng.dispose()
