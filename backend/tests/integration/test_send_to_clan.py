"""send_to_clan runs against the migrated DB (no auth schema), reads user_profiles.language,
and returns (sent, failed) counts."""

import uuid
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.services.notification as notif


@pytest.fixture()
async def engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine(migrated_db_url)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_send_to_clan_uses_user_profiles_and_counts(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    send_each = MagicMock(
        name="send_each",
        side_effect=lambda msgs: SimpleNamespace(
            responses=[SimpleNamespace(success=True, exception=None) for _ in msgs]
        ),
    )
    monkeypatch.setattr(notif.messaging, "send_each", send_each)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    clan_id, user_id = uuid.uuid4(), uuid.uuid4()
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:i,'C',:sg)"),
            {"i": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_profiles (id, email, display_name, language) "
                "VALUES (:i, :e, 'U', 'en')"
            ),
            {"i": user_id, "e": f"u-{user_id.hex[:6]}@x.io"},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_clan_roles "
                "(clan_id, user_id, role, is_approved, approved_by, approved_at) "
                "VALUES (:c, :u, 'viewer', true, :u, NOW())"
            ),
            {"c": clan_id, "u": user_id},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_fcm_tokens (user_id, token, device_platform) "
                "VALUES (:u, :t, 'android')"
            ),
            {"u": user_id, "t": f"tok-{uuid.uuid4().hex}"},
        )
        await s.commit()

    async with maker() as db:
        sent, failed = await notif.send_to_clan(
            clan_id=clan_id,
            title_key="notification.birthday.title",
            body_key="notification.birthday.body",
            db=db,
            name="An",
        )
    assert (sent, failed) == (1, 0)
    assert send_each.called  # no auth.users → no UndefinedTable crash


@pytest.mark.asyncio
async def test_send_to_clan_excludes_deactivated_members(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H1 (review 2026-07-18): a deactivated member must not receive clan push
    content. Only an explicit is_active=false excludes — the LEFT JOIN's NULL
    profile (edge case) still receives, matching the None-is-not-deactivated
    semantics of the auth chokepoint."""
    captured: list[Any] = []

    def _send_each(msgs: list[Any]) -> SimpleNamespace:
        captured.extend(msgs)
        return SimpleNamespace(
            responses=[SimpleNamespace(success=True, exception=None) for _ in msgs]
        )

    monkeypatch.setattr(notif.messaging, "send_each", MagicMock(side_effect=_send_each))
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    clan_id = uuid.uuid4()
    active_id, deact_id = uuid.uuid4(), uuid.uuid4()
    active_token = f"tok-{uuid.uuid4().hex}"
    async with maker() as s:
        await s.execute(
            sa.text("INSERT INTO clans (id, name, slug) VALUES (:i,'C',:sg)"),
            {"i": clan_id, "sg": f"c{clan_id.hex[:6]}"},
        )
        for uid, active in ((active_id, True), (deact_id, False)):
            await s.execute(
                sa.text(
                    "INSERT INTO user_profiles (id, email, display_name, is_active) "
                    "VALUES (:i, :e, 'U', :act)"
                ),
                {"i": uid, "e": f"u-{uid.hex[:6]}@x.io", "act": active},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO user_clan_roles "
                    "(clan_id, user_id, role, is_approved, approved_by, approved_at) "
                    "VALUES (:c, :u, 'viewer', true, :u, NOW())"
                ),
                {"c": clan_id, "u": uid},
            )
        await s.execute(
            sa.text(
                "INSERT INTO user_fcm_tokens (user_id, token, device_platform) "
                "VALUES (:u, :t, 'android')"
            ),
            {"u": active_id, "t": active_token},
        )
        await s.execute(
            sa.text(
                "INSERT INTO user_fcm_tokens (user_id, token, device_platform) "
                "VALUES (:u, :t, 'android')"
            ),
            {"u": deact_id, "t": f"tok-{uuid.uuid4().hex}"},
        )
        await s.commit()

    async with maker() as db:
        sent, failed = await notif.send_to_clan(
            clan_id=clan_id,
            title_key="notification.birthday.title",
            body_key="notification.birthday.body",
            db=db,
            name="An",
        )
    assert (sent, failed) == (1, 0)
    assert len(captured) == 1 and captured[0].token == active_token
