"""The 201 body of ``POST /clans/{clan_id}/invitations`` carries the link an admin shares.

ADR-062. The link is ``<INVITE_LINK_ORIGIN>/<locale>/invitations/<token>``: a page of the web
app, not the API. Before ADR-062 the body carried ``accept_path``,
``/api/v1/invitations/<token>/accept``, which answers ``POST`` only, so a relative who opened it
in a browser sent a ``GET`` and got an error.

**What these tests assert is the response body**, over HTTP, through the real route, the real
handler and a real Postgres. They pin the string. Where the string lands, the invitation page
with its heading and its ``Referrer-Policy`` header, is read in a browser by
``web/e2e/auth/invitation-link.auth.spec.ts``.

**The locale is the one the request was served in.** ``LanguageMiddleware`` sets it from the
first two letters of ``Accept-Language``, and falls back to ``vi`` when the header is absent or
names a locale ``SUPPORTED_LOCALES`` does not hold. The cases below read ``en`` and ``zh`` out of
two headers and the ``vi`` fallback out of two more, so a link that ignored the header fails the
``en`` and ``zh`` cases.

Like ``test_invitation_status_derived.py``, this overrides ``get_db`` with the plain session
maker, so nothing here is evidence about RLS on ``clan_invitations``.
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

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# The trailing slash is deliberate: an origin typed with one must not yield `//en/...`.
_ORIGIN = "https://app.example.test/"


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """The Authorization header carries ``<user_id>:<email>`` instead of a signed token."""
    assert authorization is not None, "test client must send an Authorization header"
    user_id, _, email = authorization.removeprefix("Bearer ").partition(":")
    return {"sub": user_id, "email": email, "user_metadata": {"full_name": "Test"}}


@pytest.fixture()
async def session_factory(
    migrated_db_url: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


@pytest.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[AsyncClient]:
    monkeypatch.setattr(settings, "INVITE_LINK_ORIGIN", _ORIGIN)
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture()
async def admin_in_clan(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, uuid.UUID]:
    clan_id, admin_id = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:id, 'Họ Link', :slug)"),
            {"id": clan_id, "slug": f"link-{clan_id.hex[:8]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name) VALUES (:id, :email, 'Admin')"
            ),
            {"id": admin_id, "email": f"{admin_id.hex[:8]}@example.com"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(user_id, clan_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:uid, :cid, 'admin', true, :uid, now())"
            ),
            {"uid": admin_id, "cid": clan_id},
        )
        await s.commit()
    return {"clan_id": clan_id, "admin_id": admin_id}


async def _create(
    client: AsyncClient, seeded: dict[str, uuid.UUID], accept_language: str | None
) -> dict[str, Any]:
    """Create an invitation for a fresh address and return the 201 body's ``data``."""
    clan_id, admin_id = seeded["clan_id"], seeded["admin_id"]
    headers = {
        "Authorization": f"Bearer {admin_id}:{admin_id.hex[:8]}@example.com",
        "X-Current-Clan-Id": str(clan_id),
    }
    if accept_language is not None:
        headers["Accept-Language"] = accept_language
    resp = await client.post(
        f"/api/v1/clans/{clan_id}/invitations",
        headers=headers,
        json={"email": f"invitee-{uuid.uuid4().hex[:8]}@example.com", "role": "viewer"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body.keys()) == {"data"}, body
    data: dict[str, Any] = body["data"]
    return data


async def test_the_body_carries_the_browser_link_in_the_request_locale(
    client: AsyncClient,
    admin_in_clan: dict[str, uuid.UUID],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    data = await _create(client, admin_in_clan, "en")

    assert data["invite_url"] == f"https://app.example.test/en/invitations/{data['token']}"
    assert "accept_path" not in data

    # The token in the link is the one stored for this clan, so it is the one accept will take.
    async with session_factory() as s:
        stored = await s.scalar(
            sa.text("SELECT clan_id FROM clan_invitations WHERE token = :t"),
            {"t": data["token"]},
        )
    assert stored == admin_in_clan["clan_id"]


@pytest.mark.parametrize(
    ("accept_language", "locale"),
    [(None, "vi"), ("de-DE,de;q=0.9", "vi"), ("zh-CN,zh;q=0.9,en;q=0.8", "zh")],
)
async def test_the_link_locale_follows_language_middleware(
    client: AsyncClient,
    admin_in_clan: dict[str, uuid.UUID],
    accept_language: str | None,
    locale: str,
) -> None:
    data = await _create(client, admin_in_clan, accept_language)

    assert data["invite_url"] == f"https://app.example.test/{locale}/invitations/{data['token']}"
