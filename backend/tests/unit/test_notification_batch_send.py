"""send_to_clan must batch FCM deliveries with send_each, off the event loop.

The per-token loop issued one blocking HTTPS round-trip per device: a clan
with a few hundred devices x several anniversary events put the scheduler job
runtime into minutes while it held its DB connection and the advisory lock.
send_each delivers up to 500 messages per call. Per-token semantics that must
survive batching: per-recipient locale, and unregistered-token cleanup.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from firebase_admin import messaging

import app.services.notification as notif
from app.services.translator import t

pytestmark = pytest.mark.asyncio


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeDb:
    """Async-session stand-in: serves the member SELECT, records DELETEs."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.deleted_tokens: list[str] = []

    async def execute(self, sql: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        if "DELETE" in str(sql):
            assert params is not None
            self.deleted_tokens.append(params["token"])
            return _FakeResult([])
        return _FakeResult(self._rows)


def _rows() -> list[dict[str, Any]]:
    return [
        {"user_id": uuid.uuid4(), "token": "tok-vi", "device_platform": "ios", "locale": "vi"},
        {"user_id": uuid.uuid4(), "token": "tok-en", "device_platform": "android", "locale": "en"},
        {"user_id": uuid.uuid4(), "token": "tok-dead", "device_platform": "ios", "locale": "vi"},
    ]


async def test_send_to_clan_uses_one_send_each_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {"batches": [], "on_loop": None, "single_sends": 0}

    def _fake_send_each(msgs: list[Any]) -> Any:
        try:
            asyncio.get_running_loop()
            captured["on_loop"] = True
        except RuntimeError:
            captured["on_loop"] = False
        captured["batches"].append(msgs)
        responses = []
        for m in msgs:
            if m.token == "tok-dead":
                responses.append(
                    SimpleNamespace(success=False, exception=messaging.UnregisteredError("gone"))
                )
            else:
                responses.append(SimpleNamespace(success=True, exception=None))
        return SimpleNamespace(responses=responses)

    def _fail_single_send(msg: Any) -> None:
        captured["single_sends"] += 1
        raise AssertionError("per-token messaging.send must not be used by send_to_clan")

    monkeypatch.setattr(notif.messaging, "send_each", _fake_send_each)
    monkeypatch.setattr(notif.messaging, "send", _fail_single_send)

    db = _FakeDb(_rows())
    sent, failed = await notif.send_to_clan(
        clan_id=uuid.uuid4(),
        title_key="event.upcoming",
        body_key="event.upcoming_body",
        db=db,  # type: ignore[arg-type]
    )

    assert captured["single_sends"] == 0
    assert len(captured["batches"]) == 1  # one batch, not one call per token
    assert {m.token for m in captured["batches"][0]} == {"tok-vi", "tok-en", "tok-dead"}
    assert captured["on_loop"] is False  # ran via to_thread
    assert (sent, failed) == (2, 1)
    assert db.deleted_tokens == ["tok-dead"]  # unregistered cleanup survives batching


async def test_send_to_clan_localizes_per_recipient(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[Any] = []

    def _fake_send_each(msgs: list[Any]) -> Any:
        captured.extend(msgs)
        return SimpleNamespace(
            responses=[SimpleNamespace(success=True, exception=None) for _ in msgs]
        )

    monkeypatch.setattr(notif.messaging, "send_each", _fake_send_each)
    db = _FakeDb(_rows()[:2])  # vi + en recipients
    await notif.send_to_clan(
        clan_id=uuid.uuid4(),
        title_key="event.upcoming",
        body_key="event.upcoming_body",
        db=db,  # type: ignore[arg-type]
    )
    by_token = {m.token: m for m in captured}
    assert by_token["tok-vi"].notification.title == t("event.upcoming", locale="vi")
    assert by_token["tok-en"].notification.title == t("event.upcoming", locale="en")
