"""POST /invitations/{token}/accept is rate-limited (spec 2026-07-14).

Real Postgres (migrated_db_url). JWT verification is stubbed the same way as
tests/integration/test_audit_request_meta.py (the Authorization header carries
the user id directly) since this suite is about the rate limiter, not auth —
whatever status the route ultimately returns for a bogus/unknown token or user
(404/403/whatever), it must never be 429 unless the burst limit was hit.

The app's RateLimitMiddleware instance (added by ``create_app()`` with the
production ``max_requests=20``) is reconfigured to a small limit here for test
speed. This is safe because Starlette only builds its middleware stack lazily
on the first request (``Starlette.build_middleware_stack``, cached on
``app.middleware_stack``), so mutating the ``Middleware(...)`` entry's kwargs
in ``app.user_middleware`` before the first request still takes effect.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from fastapi import Header
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.rate_limit import RateLimitMiddleware
from app.core.security import get_current_user
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _override_current_user(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    assert authorization is not None, "test client must send an Authorization header"
    return {"sub": authorization.removeprefix("Bearer ")}


@pytest.fixture()
async def client_with_rate_limit(migrated_db_url: str) -> AsyncGenerator[AsyncClient]:
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user

    for mw in app.user_middleware:
        if mw.cls is RateLimitMiddleware:  # type: ignore[comparison-overlap]
            mw.kwargs["max_requests"] = 5
            break
    else:
        raise AssertionError("RateLimitMiddleware not found in app.user_middleware")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    await engine.dispose()


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {uuid.uuid4()}"}


async def test_invitation_accept_throttled_after_burst(
    client_with_rate_limit: AsyncClient, auth_headers: dict[str, str]
) -> None:
    for _ in range(5):
        r = await client_with_rate_limit.post(
            "/api/v1/invitations/deadbeef/accept", headers=auth_headers
        )
        assert r.status_code != 429
    r = await client_with_rate_limit.post(
        "/api/v1/invitations/deadbeef/accept", headers=auth_headers
    )
    assert r.status_code == 429
    assert "retry-after" in {k.lower() for k in r.headers}
    assert r.json()["error"]["code"] == "rate_limited"


async def test_non_covered_path_not_throttled(
    client_with_rate_limit: AsyncClient, auth_headers: dict[str, str]
) -> None:
    for _ in range(10):
        r = await client_with_rate_limit.get("/api/v1/persons", headers=auth_headers)
        assert r.status_code != 429
