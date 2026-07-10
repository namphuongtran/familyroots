"""FCM send is off-loaded to a thread; invalid-token cleanup does not commit."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.notification as notif


@pytest.mark.asyncio
async def test_send_uses_to_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    async def fake_to_thread(fn, *a, **k):
        captured["fn"] = fn
        return None

    monkeypatch.setattr(notif.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(notif.messaging, "send", MagicMock(name="send"))
    ok = await notif.send_push_notification(
        "tok", "notification.birthday.title", "notification.birthday.body", locale="en"
    )
    assert ok is True
    assert captured["fn"] is notif.messaging.send  # the sync SDK call was off-loaded


@pytest.mark.asyncio
async def test_remove_invalid_token_does_not_commit() -> None:
    db = AsyncMock()
    await notif._remove_invalid_token("tok", db)
    db.execute.assert_awaited_once()
    db.commit.assert_not_called()  # must not commit the shared broadcast session
