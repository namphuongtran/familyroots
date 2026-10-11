"""The purge job's sweep of unconfirmed staged uploads (ADR-068).

Runs the real ``SupabaseStorageAdapter`` listing over a fake storage3 bucket that answers
``list`` the way Storage does: one folder level at a time, folders with ``id: None``, and
pages of at most ``limit`` entries. The reading is which objects are left afterwards.

Negative control, run 2026-10-11: with the adapter listing ``documents/`` instead of
``uploads/``, ``test_the_sweep_deletes_only_staged_uploads_older_than_the_cutoff`` fails:
the old confirmed blob is deleted and the old staged files survive.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.infrastructure.storage.supabase_adapter import SupabaseStorageAdapter
from app.services.document_purge import STAGED_UPLOAD_MAX_AGE, _sweep_staged_uploads

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


class FakeBucket:
    """The storage3 file API, reduced to ``list`` and ``remove`` over a flat key space."""

    def __init__(self, objects: dict[str, datetime]) -> None:
        self.objects = dict(objects)
        self.list_calls: list[tuple[str, int, int]] = []

    def list(self, prefix: str, options: dict[str, Any]) -> list[dict[str, Any]]:
        limit, offset = options["limit"], options["offset"]
        self.list_calls.append((prefix, limit, offset))
        children: dict[str, dict[str, Any]] = {}
        for key, created in self.objects.items():
            if not key.startswith(prefix + "/"):
                continue
            head, _, rest = key[len(prefix) + 1 :].partition("/")
            if rest:
                children.setdefault(head, {"name": head, "id": None, "created_at": None})
            else:
                children[head] = {
                    "name": head,
                    "id": f"id-{key}",
                    "created_at": created.isoformat().replace("+00:00", "Z"),
                    "metadata": {"size": 10},
                }
        ordered = [children[name] for name in sorted(children)]
        return ordered[offset : offset + limit]

    # Annotated without `list`: inside this class the name means the method above.
    def remove(self, paths: Iterable[str]) -> object:
        for path in paths:
            self.objects.pop(path, None)
        return None


def _install(monkeypatch: pytest.MonkeyPatch, bucket: FakeBucket) -> None:
    from unittest.mock import MagicMock

    from app.infrastructure.storage import supabase_adapter as mod

    client = MagicMock()
    client.storage.from_.return_value = bucket
    monkeypatch.setattr(mod, "get_service_client", lambda: client)


async def test_the_sweep_deletes_only_staged_uploads_older_than_the_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old, fresh = NOW - timedelta(hours=30), NOW - timedelta(hours=1)
    many_old = {f"clans/c3/uploads/{i:04d}.png": old for i in range(120)}  # > one page
    bucket = FakeBucket(
        {
            "clans/c1/uploads/old.png": old,
            "clans/c1/uploads/fresh.png": fresh,
            "clans/c1/documents/old.png": old,
            "clans/c1/avatars/person-1": old,
            "clans/c2/uploads/old.jpg": NOW - timedelta(hours=48),
            **many_old,
        }
    )
    _install(monkeypatch, bucket)

    await _sweep_staged_uploads(SupabaseStorageAdapter(), NOW - STAGED_UPLOAD_MAX_AGE)

    assert set(bucket.objects) == {
        "clans/c1/uploads/fresh.png",
        "clans/c1/documents/old.png",
        "clans/c1/avatars/person-1",
    }
    # The 120 staged files took two pages of the one clan folder that holds them.
    assert ("clans/c3/uploads", 100, 100) in bucket.list_calls


async def test_a_failed_listing_leaves_everything_for_the_next_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenBucket(FakeBucket):
        def list(self, prefix: str, options: dict[str, Any]) -> list[dict[str, Any]]:
            raise ConnectionError("storage down")

    bucket = BrokenBucket({"clans/c1/uploads/old.png": NOW - timedelta(hours=30)})
    _install(monkeypatch, bucket)

    await _sweep_staged_uploads(SupabaseStorageAdapter(), NOW - STAGED_UPLOAD_MAX_AGE)

    assert set(bucket.objects) == {"clans/c1/uploads/old.png"}
