"""ADR-036 — `PATCH /documents/{id}/set-avatar` is the only writer of avatar_url.

Real Postgres (`migrated_db_url`), real RBAC, real Person + Document aggregates and
repositories, through the real HTTP router. Only JWT *verification* is stubbed (the
Authorization header carries the user id, as in test_document_soft_delete.py) and the
storage adapter is a spy so nothing touches Supabase.

What each test proves is stated on the test. The load-bearing ones:

* **Two-sided clan isolation.** Clan A sets an avatar. Clan B — a real clan with a
  real admin — cannot set it, cannot overwrite it, cannot redirect it, and cannot
  make the backend publish clan A's object. Verified from both directions, and by
  inspecting what was actually handed to the storage adapter, because a public bucket
  is where an isolation mistake becomes permanently visible to strangers.
* **Never a presigned URL.** The column must never hold a URL that expires.
* **Fail closed on a misconfigured bucket.** 503 with a mapped code, and no row
  touched — not a 500, and not a silent success writing a dead URL.
* **Negative control** (`test_negative_control_*`): shows the guard is what produces
  the isolation, by exercising the same request the guard rejects, one clan over.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import get_current_user
from app.domain.document.repository import (
    DEFAULT_PRESIGN_TTL,
    StorageBucketNotConfiguredError,
)
from app.infrastructure.dependencies import get_document_command_handler
from app.main import create_app
from app.services.translator import load_translations

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_PUBLIC_BASE = "https://proj.supabase.co/storage/v1/object/public/family-roots-avatars"


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


class FakeStorage:
    """StoragePort spy. Records every publish so a test can assert *which* object
    would have been made world-readable, not merely that the request 200'd."""

    def __init__(self) -> None:
        self.uploaded: list[str] = []
        self.published: list[tuple[str, str]] = []
        self.presigned: list[str] = []
        self.publish_error: Exception | None = None
        self.publish_override: str | None = None

    async def upload(self, path: str, content: bytes, content_type: str | None) -> str:
        self.uploaded.append(path)
        return path

    async def delete(self, storage_path: str) -> bool:
        return True

    async def get_presigned_url(
        self, storage_path: str, expires_in: int = DEFAULT_PRESIGN_TTL
    ) -> str:
        self.presigned.append(storage_path)
        return f"https://signed.example/{storage_path}?token=abc&expires={expires_in}"

    async def publish_public(
        self, *, source_path: str, destination_path: str, content_type: str | None
    ) -> str:
        if self.publish_error is not None:
            raise self.publish_error
        self.published.append((source_path, destination_path))
        if self.publish_override is not None:
            return self.publish_override
        return f"{_PUBLIC_BASE}/{destination_path}"


@pytest.fixture()
async def session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


async def _seed_clan(
    s: AsyncSession, label: str
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """One clan + an approved admin + a member person + that person's photo document."""
    clan_id, admin_id, person_id, doc_id = (uuid.uuid4() for _ in range(4))
    await s.execute(
        sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, :name, :slug)"),
        {"id": clan_id, "name": f"Clan {label}", "slug": f"{label}-{clan_id.hex[:8]}"},
    )
    await s.execute(
        sa.text("INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :email, :name)"),
        {"id": admin_id, "email": f"{admin_id.hex[:8]}@example.com", "name": f"admin-{label}"},
    )
    await s.execute(
        sa.text(
            "INSERT INTO user_clan_roles "
            "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
            "VALUES (:uid, :cid, 'admin', true, :uid, now())"
        ),
        {"uid": admin_id, "cid": clan_id},
    )
    await s.execute(
        sa.text(
            "INSERT INTO persons (id, full_name, gender, created_by_clan_id, created_by) "
            "VALUES (:id, :name, 'male', :cid, :uid)"
        ),
        {"id": person_id, "name": f"Nguyễn Văn {label.upper()}", "cid": clan_id, "uid": admin_id},
    )
    await s.execute(
        sa.text(
            "INSERT INTO clan_memberships (person_id, clan_id, joined_at) "
            "VALUES (:pid, :cid, now())"
        ),
        {"pid": person_id, "cid": clan_id},
    )
    await s.execute(
        sa.text(
            "INSERT INTO documents "
            "(id, clan_id, person_id, title, document_type, storage_path, mime_type, created_by) "
            "VALUES (:id, :cid, :pid, 'Ảnh thờ', 'photo', :path, 'image/jpeg', :uid)"
        ),
        {
            "id": doc_id,
            "cid": clan_id,
            "pid": person_id,
            "path": f"clans/{clan_id}/documents/{doc_id}.jpg",
            "uid": admin_id,
        },
    )
    return clan_id, admin_id, person_id, doc_id


@pytest.fixture()
async def seeded(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """Two fully independent clans, A and B, each with its own admin, person, photo."""
    async with session_factory() as s:
        a_clan, a_admin, a_person, a_doc = await _seed_clan(s, "a")
        b_clan, b_admin, b_person, b_doc = await _seed_clan(s, "b")
        await s.commit()
    return {
        "a": {"clan": a_clan, "admin": a_admin, "person": a_person, "doc": a_doc},
        "b": {"clan": b_clan, "admin": b_admin, "person": b_person, "doc": b_doc},
    }


@pytest.fixture()
def fake_storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession],
    fake_storage: FakeStorage,
) -> AsyncGenerator[AsyncClient]:
    from app.application.document.handlers import DocumentCommandHandler
    from app.infrastructure.event_dispatcher import create_event_dispatcher
    from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
    from app.infrastructure.persistence.person_repository import SqlAlchemyPersonRepository
    from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

    app = create_app()
    load_translations()  # no lifespan here; localized messages need explicit loading

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    async def _make_cmd_handler() -> AsyncGenerator[Any]:
        async with session_factory() as db:
            uow = SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))
            yield DocumentCommandHandler(
                SqlAlchemyDocumentRepository(uow),
                fake_storage,
                uow,
                SqlAlchemyPersonRepository(uow),
            )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_document_command_handler] = _make_cmd_handler

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def _headers(side: dict[str, Any]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {side['admin']}",
        "X-Current-Clan-Id": str(side["clan"]),
    }


async def _avatar_url(session_factory: Any, person_id: uuid.UUID) -> str | None:
    """Read the column straight from Postgres — never through a response DTO, so the
    assertions are about what is actually stored."""
    async with session_factory() as s:
        stored = (
            await s.execute(
                sa.text("SELECT avatar_url FROM persons WHERE id = :id"), {"id": person_id}
            )
        ).scalar_one()
    assert stored is None or isinstance(stored, str)
    return stored


# ── The happy path ────────────────────────────────────────────────────────────


async def test_set_avatar_publishes_and_stores_a_permanent_public_url(
    client: AsyncClient,
    seeded: dict[str, Any],
    fake_storage: FakeStorage,
    session_factory: Any,
) -> None:
    a = seeded["a"]
    resp = await client.patch(f"/api/v1/documents/{a['doc']}/set-avatar", headers=_headers(a))
    assert resp.status_code == 200, resp.text

    body = resp.json()["data"]
    expected_path = f"clans/{a['clan']}/avatars/{a['person']}"
    assert body["avatar_url"] == f"{_PUBLIC_BASE}/{expected_path}"

    # The blob copied is A's own document, into A's own avatar path.
    assert fake_storage.published == [
        (f"clans/{a['clan']}/documents/{a['doc']}.jpg", expected_path)
    ]
    # And the column now holds exactly that URL.
    assert await _avatar_url(session_factory, a["person"]) == body["avatar_url"]

    async with session_factory() as s:
        assert (
            await s.execute(
                sa.text("SELECT is_avatar FROM documents WHERE id = :id"), {"id": a["doc"]}
            )
        ).scalar_one() is True


async def test_stored_url_is_never_a_presigned_url(
    client: AsyncClient,
    seeded: dict[str, Any],
    fake_storage: FakeStorage,
    session_factory: Any,
) -> None:
    """The whole reason this decision was needed: a presigned URL in a permanent
    column rots silently. Assert the shape, and that no presign was even minted."""
    a = seeded["a"]
    resp = await client.patch(f"/api/v1/documents/{a['doc']}/set-avatar", headers=_headers(a))
    assert resp.status_code == 200, resp.text

    stored = await _avatar_url(session_factory, a["person"])
    assert stored is not None
    assert "?" not in stored and "#" not in stored
    assert "token=" not in stored and "X-Amz-" not in stored
    assert "/object/sign/" not in stored
    assert "/object/public/" in stored
    assert fake_storage.presigned == []  # set-avatar no longer presigns at all


async def test_a_presigned_url_from_storage_is_refused_and_nothing_is_written(
    client: AsyncClient,
    seeded: dict[str, Any],
    fake_storage: FakeStorage,
    session_factory: Any,
) -> None:
    """If a future adapter regressed to returning a signed URL, the domain refuses it
    rather than let the column start expiring. 422, and the row is untouched."""
    a = seeded["a"]
    fake_storage.publish_override = "https://proj.supabase.co/x.jpg?token=abc&expires=1"

    resp = await client.patch(f"/api/v1/documents/{a['doc']}/set-avatar", headers=_headers(a))

    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "person.avatar_url_not_permanent"
    assert await _avatar_url(session_factory, a["person"]) is None


# ── Two-sided clan isolation ──────────────────────────────────────────────────


async def test_clan_b_cannot_set_an_avatar_from_clan_as_document(
    client: AsyncClient,
    seeded: dict[str, Any],
    fake_storage: FakeStorage,
    session_factory: Any,
) -> None:
    """Side 1: B, acting in its own clan, names A's document id. 404, and — the part
    that matters for a public bucket — the backend publishes nothing at all."""
    a, b = seeded["a"], seeded["b"]

    resp = await client.patch(f"/api/v1/documents/{a['doc']}/set-avatar", headers=_headers(b))

    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "document_not_found"
    assert fake_storage.published == []
    assert await _avatar_url(session_factory, a["person"]) is None


async def test_clan_b_cannot_borrow_clan_as_clan_header(
    client: AsyncClient,
    seeded: dict[str, Any],
    fake_storage: FakeStorage,
    session_factory: Any,
) -> None:
    """Side 2: B's admin sends A's clan id in X-Current-Clan-Id. The role check for
    clan A fails, so B never reaches the publish path."""
    a, b = seeded["a"], seeded["b"]

    resp = await client.patch(
        f"/api/v1/documents/{a['doc']}/set-avatar",
        headers={"Authorization": f"Bearer {b['admin']}", "X-Current-Clan-Id": str(a["clan"])},
    )

    assert resp.status_code in (403, 404), resp.text
    assert fake_storage.published == []
    assert await _avatar_url(session_factory, a["person"]) is None


async def test_clan_b_cannot_overwrite_or_redirect_an_avatar_clan_a_already_set(
    client: AsyncClient,
    seeded: dict[str, Any],
    fake_storage: FakeStorage,
    session_factory: Any,
) -> None:
    """The published-object case: A's avatar is live. B tries again — by document id
    and by clan header — and neither the column nor the public object changes."""
    a, b = seeded["a"], seeded["b"]

    first = await client.patch(f"/api/v1/documents/{a['doc']}/set-avatar", headers=_headers(a))
    assert first.status_code == 200, first.text
    original = await _avatar_url(session_factory, a["person"])
    published_after_a = list(fake_storage.published)

    for headers in (
        _headers(b),
        {"Authorization": f"Bearer {b['admin']}", "X-Current-Clan-Id": str(a["clan"])},
    ):
        resp = await client.patch(f"/api/v1/documents/{a['doc']}/set-avatar", headers=headers)
        assert resp.status_code in (403, 404), resp.text

    assert await _avatar_url(session_factory, a["person"]) == original
    assert fake_storage.published == published_after_a  # no second publish happened


async def test_negative_control_the_same_request_succeeds_for_the_owning_clan(
    client: AsyncClient,
    seeded: dict[str, Any],
    fake_storage: FakeStorage,
    session_factory: Any,
) -> None:
    """NEGATIVE CONTROL. The request rejected above is byte-identical apart from which
    clan sends it; here the owning clan sends it and it succeeds. This fails if the
    isolation checks were removed — a blanket 404 would pass the isolation tests while
    breaking the feature — and it fails if the feature never worked at all."""
    a = seeded["a"]

    resp = await client.patch(f"/api/v1/documents/{a['doc']}/set-avatar", headers=_headers(a))

    assert resp.status_code == 200, resp.text
    assert len(fake_storage.published) == 1
    source, destination = fake_storage.published[0]
    assert source.startswith(f"clans/{a['clan']}/")
    assert destination.startswith(f"clans/{a['clan']}/")
    assert await _avatar_url(session_factory, a["person"]) is not None
    # And clan B's person was not collaterally touched.
    assert await _avatar_url(session_factory, seeded["b"]["person"]) is None


async def test_published_object_paths_never_collide_across_clans(
    client: AsyncClient,
    seeded: dict[str, Any],
    fake_storage: FakeStorage,
) -> None:
    """Both clans set an avatar. The two public keys must differ by clan prefix — in a
    shared public bucket, a colliding key is one clan silently serving another's photo."""
    a, b = seeded["a"], seeded["b"]

    assert (
        await client.patch(f"/api/v1/documents/{a['doc']}/set-avatar", headers=_headers(a))
    ).status_code == 200
    assert (
        await client.patch(f"/api/v1/documents/{b['doc']}/set-avatar", headers=_headers(b))
    ).status_code == 200

    destinations = [dest for _, dest in fake_storage.published]
    assert destinations == [
        f"clans/{a['clan']}/avatars/{a['person']}",
        f"clans/{b['clan']}/avatars/{b['person']}",
    ]
    assert len(set(destinations)) == 2


# ── Client writes to avatar_url ───────────────────────────────────────────────


async def test_patch_person_cannot_write_avatar_url(
    client: AsyncClient, seeded: dict[str, Any], session_factory: Any
) -> None:
    """A direct client write is rejected (422), not quietly accepted — including the
    external URL that would make this field an SSRF / tracking-pixel surface."""
    a = seeded["a"]

    resp = await client.patch(
        f"/api/v1/persons/{a['person']}",
        headers=_headers(a),
        json={"expected_version": 1, "avatar_url": "https://evil.example/pixel.gif"},
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "validation_error"
    assert "body.avatar_url" in resp.json()["error"]["detail"]["fields"]
    assert await _avatar_url(session_factory, a["person"]) is None


async def test_patch_person_still_updates_other_fields(
    client: AsyncClient, seeded: dict[str, Any], session_factory: Any
) -> None:
    """Negative control for the rejection: the same endpoint keeps working for every
    field that is *not* avatar_url, so the 422 above is specific, not a broken PATCH."""
    a = seeded["a"]

    resp = await client.patch(
        f"/api/v1/persons/{a['person']}",
        headers=_headers(a),
        json={"expected_version": 1, "occupation": "Thầy giáo"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["occupation"] == "Thầy giáo"


async def test_post_person_cannot_seed_avatar_url(
    client: AsyncClient, seeded: dict[str, Any]
) -> None:
    a = seeded["a"]
    resp = await client.post(
        "/api/v1/persons",
        headers=_headers(a),
        json={"full_name": "Nguyễn Văn C", "avatar_url": "https://evil.example/pixel.gif"},
    )
    assert resp.status_code == 422, resp.text
    assert "body.avatar_url" in resp.json()["error"]["detail"]["fields"]


# ── Misconfigured bucket ──────────────────────────────────────────────────────


async def test_missing_public_bucket_is_a_mapped_503_and_writes_nothing(
    client: AsyncClient,
    seeded: dict[str, Any],
    fake_storage: FakeStorage,
    session_factory: Any,
) -> None:
    """The bucket is an owner action this code cannot perform. Until it exists the
    endpoint must fail closed with a clear mapped code — never a 500, and never a
    "success" that leaves a person pointing at a URL that will never resolve."""
    a = seeded["a"]
    fake_storage.publish_error = StorageBucketNotConfiguredError("bucket missing")

    resp = await client.patch(f"/api/v1/documents/{a['doc']}/set-avatar", headers=_headers(a))

    assert resp.status_code == 503, resp.text
    error = resp.json()["error"]
    assert error["code"] == "storage_bucket_not_configured"
    assert error["message"] and error["message"] != "error.storage_bucket_not_configured"

    # Nothing half-applied: no URL, and the document is not flagged as the avatar.
    assert await _avatar_url(session_factory, a["person"]) is None
    async with session_factory() as s:
        assert (
            await s.execute(
                sa.text("SELECT is_avatar FROM documents WHERE id = :id"), {"id": a["doc"]}
            )
        ).scalar_one() is False


# ── Audit ─────────────────────────────────────────────────────────────────────


async def test_set_avatar_is_audited_with_the_published_url(
    client: AsyncClient, seeded: dict[str, Any], session_factory: Any
) -> None:
    """The write flows through the UoW + domain events, so both the document action
    and the person field change land in audit_logs in the same transaction."""
    a = seeded["a"]
    resp = await client.patch(f"/api/v1/documents/{a['doc']}/set-avatar", headers=_headers(a))
    assert resp.status_code == 200, resp.text

    async with session_factory() as s:
        rows = (
            (
                await s.execute(
                    sa.text(
                        "SELECT action, new_value FROM audit_logs "
                        "WHERE clan_id = :cid ORDER BY created_at"
                    ),
                    {"cid": a["clan"]},
                )
            )
            .mappings()
            .all()
        )

    # Both halves are recorded: the document action AND the person field edit
    # (PersonUpdated, emitted by set_avatar_url) — so a member acquiring a public URL
    # is attributable to an actor, not an unexplained column change.
    actions = [r["action"] for r in rows]
    assert actions == ["document.set_avatar", "person.update"], actions
    by_action = {r["action"]: r["new_value"] for r in rows}
    published = resp.json()["data"]["avatar_url"]
    assert by_action["document.set_avatar"]["avatar_url"] == published
    assert by_action["person.update"]["avatar_url"] == published
