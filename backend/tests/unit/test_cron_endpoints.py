"""The two Vercel Cron routes run their job only for `Authorization: Bearer <CRON_SECRET>`.

ADR-065. Each test drives a route over HTTP and reads two things: the response, and whether
the job ran. Both jobs are replaced with spies at the attribute the route calls through
(``app.services.scheduler.send_anniversary_notifications``,
``app.services.document_purge.purge_expired_documents``), so no database is needed. The
integration test beside this one, ``tests/integration/test_cron_endpoints_run_the_jobs.py``,
runs the real jobs through the same routes.

Every refusal must be the bare 404 that a path which does not exist gets (ADR-021,
ADR-040). The comparison is byte for byte, because a refusal that differs in any way tells
a scanner the route is there.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.cron import ANNIVERSARY_NOTIFICATIONS_PATH, DOCUMENT_PURGE_PATH
from app.core.config import MIN_METRICS_TOKEN_LENGTH, settings
from app.main import create_app

pytestmark = pytest.mark.unit

# Exactly at the floor, assembled from pieces so it reads as a placeholder rather than a
# leaked credential (see _TOKEN in test_metrics_endpoint.py for why).
_SECRET = (("not-a-real-secret-" + "0123456789abcdef") * 2)[:MIN_METRICS_TOKEN_LENGTH]


@dataclass
class _Spies:
    anniversary: AsyncMock
    purge: AsyncMock

    def for_path(self, path: str) -> AsyncMock:
        return self.anniversary if path == ANNIVERSARY_NOTIFICATIONS_PATH else self.purge

    def other_than(self, path: str) -> AsyncMock:
        return self.purge if path == ANNIVERSARY_NOTIFICATIONS_PATH else self.anniversary


@pytest.fixture
def spies(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Spies]:
    found = _Spies(anniversary=AsyncMock(), purge=AsyncMock())
    monkeypatch.setattr("app.services.scheduler.send_anniversary_notifications", found.anniversary)
    monkeypatch.setattr("app.services.document_purge.purge_expired_documents", found.purge)
    yield found


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


_PATHS = pytest.mark.parametrize("path", [ANNIVERSARY_NOTIFICATIONS_PATH, DOCUMENT_PURGE_PATH])


def _not_found_for_a_path_that_does_not_exist(client: TestClient) -> tuple[int, bytes, str]:
    response = client.get("/internal/cron/no-such-job")
    return response.status_code, response.content, response.headers["content-type"]


# ── refusals ──────────────────────────────────────────────────────────────────


@_PATHS
def test_no_authorization_header_is_404_and_the_job_does_not_run(
    path: str, client: TestClient, spies: _Spies, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CRON_SECRET", _SECRET)
    response = client.get(path)
    assert response.status_code == 404
    assert spies.for_path(path).await_count == 0


@_PATHS
@pytest.mark.parametrize(
    "presented",
    [
        "Bearer wrong",
        _SECRET,  # the secret, without the scheme
        f"bearer {_SECRET}",  # the scheme is matched exactly, as Vercel sends it
        f"Bearer {_SECRET} ",
        f"Bearer {_SECRET[:-1]}",
        f"Bearer {_SECRET}x",
        f"Basic {_SECRET}",
    ],
)
def test_a_wrong_secret_is_404_and_the_job_does_not_run(
    path: str,
    presented: str,
    client: TestClient,
    spies: _Spies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CRON_SECRET", _SECRET)
    response = client.get(path, headers={"Authorization": presented})
    assert response.status_code == 404
    assert spies.for_path(path).await_count == 0


@_PATHS
@pytest.mark.parametrize("presented", [None, "Bearer ", "Bearer"])
def test_an_empty_cron_secret_is_404_whatever_is_presented(
    path: str,
    presented: str | None,
    client: TestClient,
    spies: _Spies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default. "Bearer " is exactly what an empty secret would expect, so this is the
    case that a comparison alone would let through."""
    monkeypatch.setattr(settings, "CRON_SECRET", "")
    headers = {} if presented is None else {"Authorization": presented}
    response = client.get(path, headers=headers)
    assert response.status_code == 404
    assert spies.for_path(path).await_count == 0


@_PATHS
@pytest.mark.parametrize(
    "weak",
    [
        "short-secret",
        _SECRET[:-1],  # one below the length floor
        "a" * 64,  # long, but one distinct character
    ],
)
def test_a_weak_cron_secret_serves_nothing_even_to_the_matching_header(
    path: str,
    weak: str,
    client: TestClient,
    spies: _Spies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation enforces the floor only in production with the scheduler off, so the
    handler re-checks it everywhere, as /internal/metrics does (ADR-040)."""
    monkeypatch.setattr(settings, "CRON_SECRET", weak)
    response = client.get(path, headers={"Authorization": f"Bearer {weak}"})
    assert response.status_code == 404
    assert spies.for_path(path).await_count == 0


@_PATHS
def test_a_non_ascii_header_is_404_not_500(
    path: str, client: TestClient, spies: _Spies, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CRON_SECRET", _SECRET)
    response = client.get(path, headers={b"Authorization": b"Bearer caf\xc3\xa9"})
    assert response.status_code == 404
    assert spies.for_path(path).await_count == 0


@_PATHS
def test_every_refusal_is_byte_identical_to_a_path_that_does_not_exist(
    path: str, client: TestClient, spies: _Spies, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = _not_found_for_a_path_that_does_not_exist(client)
    assert expected[0] == 404

    monkeypatch.setattr(settings, "CRON_SECRET", _SECRET)
    for headers in ({}, {"Authorization": "Bearer wrong"}):
        response = client.get(path, headers=headers)
        assert (response.status_code, response.content, response.headers["content-type"]) == (
            expected
        )
    monkeypatch.setattr(settings, "CRON_SECRET", "")
    response = client.get(path, headers={"Authorization": f"Bearer {_SECRET}"})
    assert (response.status_code, response.content, response.headers["content-type"]) == (expected)
    assert spies.for_path(path).await_count == 0


# ── success ───────────────────────────────────────────────────────────────────


@_PATHS
def test_the_right_secret_runs_that_job_once_and_only_that_job(
    path: str, client: TestClient, spies: _Spies, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CRON_SECRET", _SECRET)
    response = client.get(path, headers={"Authorization": f"Bearer {_SECRET}"})
    assert response.status_code == 204
    assert response.content == b""
    assert spies.for_path(path).await_count == 1
    # Called with no arguments, so the job uses its production defaults ("today", "now").
    spies.for_path(path).assert_awaited_once_with()
    assert spies.other_than(path).await_count == 0


@_PATHS
def test_a_job_fatal_error_is_a_500_not_a_success(
    path: str, client: TestClient, spies: _Spies, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Vercel does not retry a failed cron run, and reads only the status. A job that
    raised must not report 204."""
    monkeypatch.setattr(settings, "CRON_SECRET", _SECRET)
    spies.for_path(path).side_effect = RuntimeError("database went away")
    response = client.get(path, headers={"Authorization": f"Bearer {_SECRET}"})
    assert response.status_code == 500
    assert spies.for_path(path).await_count == 1


# ── off the public surfaces ───────────────────────────────────────────────────


def test_the_cron_routes_are_hidden_from_openapi(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert ANNIVERSARY_NOTIFICATIONS_PATH not in paths
    assert DOCUMENT_PURGE_PATH not in paths


def test_the_cron_routes_are_excluded_from_prometheus(
    client: TestClient, spies: _Spies, monkeypatch: pytest.MonkeyPatch
) -> None:
    metrics_token = (("not-a-real-token-" + "0123456789abcdef") * 2)[:MIN_METRICS_TOKEN_LENGTH]
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", metrics_token)
    monkeypatch.setattr(settings, "CRON_SECRET", _SECRET)

    # Control: an ordinary route IS recorded, so an empty exposition cannot pass this.
    client.get("/api/v1/persons")
    for path in (ANNIVERSARY_NOTIFICATIONS_PATH, DOCUMENT_PURGE_PATH):
        assert client.get(path, headers={"Authorization": f"Bearer {_SECRET}"}).status_code == 204
        assert client.get(path).status_code == 404

    body = client.get("/internal/metrics", headers={"X-Metrics-Token": metrics_token}).text
    assert 'handler="/api/v1/persons"' in body
    assert 'handler="/internal/cron/' not in body, [
        line for line in body.splitlines() if "/internal/cron/" in line
    ]
