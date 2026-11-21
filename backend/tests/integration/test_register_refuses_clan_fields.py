"""``POST /auth/register`` refuses every clan field (ADR-075 amendment, #331).

A clan is created or joined only in onboarding, after the email is confirmed. These
tests send the request and read the response body and the ``clans`` table, rather than
asking whether a schema field exists.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Iterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.infrastructure.dependencies import get_identity_provider
from app.main import create_app

pytestmark = pytest.mark.integration

_BASE = {"password": "S3cure!pass", "full_name": "Người Mới"}


@pytest.fixture()
def identity() -> AsyncMock:
    return AsyncMock()


@pytest.fixture()
def client(migrated_db_url: str, identity: AsyncMock) -> Iterator[TestClient]:
    app = create_app()
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_identity_provider] = lambda: identity
    yield TestClient(app)
    engine.sync_engine.dispose()


def _clan_count(dsn: str, slug: str) -> int:
    engine = sa.create_engine(dsn)
    try:
        with engine.connect() as conn:
            return int(
                conn.execute(
                    sa.text("SELECT count(*) FROM clans WHERE slug = :s"), {"s": slug}
                ).scalar_one()
            )
    finally:
        engine.dispose()


def test_register_with_clan_action_create_is_422_and_creates_no_clan(
    client: TestClient, identity: AsyncMock, migrated_db_url: str
) -> None:
    slug = f"refused-{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/v1/auth/register",
        json={
            **_BASE,
            "email": f"{slug}@example.com",
            "clan_action": "create",
            "clan_name": "Họ Bị Từ Chối",
            "clan_slug": slug,
        },
    )
    assert resp.status_code == 422, resp.text
    error = resp.json()["error"]
    assert error["code"] == "auth.register_names_no_clan", resp.text
    assert error["detail"]["fields"] == ["clan_action", "clan_name", "clan_slug"]
    assert _clan_count(migrated_db_url, slug) == 0
    identity.create_user.assert_not_awaited()


@pytest.mark.parametrize(
    "field",
    ["clan_action", "clan_code", "clan_id", "clan_name", "clan_slug"],
)
def test_each_clan_field_alone_is_refused(
    client: TestClient, identity: AsyncMock, field: str
) -> None:
    value: Any = {"clan_action": "join", "clan_id": str(uuid.uuid4())}.get(field, "ho-moi")
    resp = client.post(
        "/api/v1/auth/register",
        json={**_BASE, "email": f"{uuid.uuid4().hex[:8]}@example.com", field: value},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "auth.register_names_no_clan", resp.text
    identity.create_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_clanless_body_still_registers_and_writes_no_clan(
    client: TestClient, identity: AsyncMock, migrated_db_url: str
) -> None:
    """The refusal is not a blanket 422: the same body without clan fields is a 201."""
    identity.create_user.return_value = str(uuid.uuid4())
    engine = create_async_engine(migrated_db_url)
    async with engine.connect() as conn:
        before = (await conn.execute(sa.text("SELECT count(*) FROM clans"))).scalar_one()
    resp = client.post(
        "/api/v1/auth/register",
        json={**_BASE, "email": f"{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert resp.status_code == 201, resp.text
    async with engine.connect() as conn:
        after = (await conn.execute(sa.text("SELECT count(*) FROM clans"))).scalar_one()
    await engine.dispose()
    assert after == before
