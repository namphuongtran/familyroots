"""Two app instances on one shared store refuse at one budget between them (ADR-072, #257).

On Vercel Functions the backend runs as many instances, and each built its own
``RateLimitMiddleware`` with its own count, so a burst spread over instances was admitted
once per instance. Measured 2026-10-11 against production: 40 concurrent requests from one
address, 34 admitted. Two ``create_app()`` instances here stand for two Vercel instances.

The store is ``UpstashRateLimitStore``, the adapter production runs, pointed at a real Redis
through ``serverless-redis-http``, which answers Upstash's REST API. Locally it is
``docker compose up -d redis-http``; CI runs it as a service. Override the address with
``TEST_UPSTASH_URL`` and ``TEST_UPSTASH_TOKEN``. When it cannot be reached the module fails,
it does not skip: a skipped reading would let the shared count go unread in a green suite.

The reading is the status codes of 40 concurrent ``POST /api/v1/auth/login`` with body ``{}``,
split evenly between the two apps. That route is counted, and with that body it answers 422
at request validation, before the handler runs, so 422 means admitted and 429 means refused.
The negative control is the same 40 over two in-memory stores, which admits all of them.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections import Counter
from collections.abc import AsyncIterator

import httpx2
import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

import app.main as main_module
from app.core.config import Settings
from app.core.database import get_db
from app.core.rate_limit import InMemoryRateLimitStore, RateLimitStore
from app.infrastructure.upstash_rate_limit_store import UpstashRateLimitStore
from app.main import create_app

pytestmark = pytest.mark.integration

UPSTASH_URL = os.environ.get("TEST_UPSTASH_URL", "http://127.0.0.1:8079")
# docker-compose.yml's SRH_TOKEN: the emulator's own, not a secret.
UPSTASH_TOKEN = os.environ.get("TEST_UPSTASH_TOKEN", "familyroots-local-redis-http")

_BUDGET = 20
_BURST = 40


async def _no_db() -> AsyncIterator[None]:
    yield None


@pytest.fixture()
async def emulator() -> None:
    """Fail, naming the remedy, when serverless-redis-http is not answering."""
    async with httpx2.AsyncClient(timeout=2) as client:
        try:
            response = await client.post(
                UPSTASH_URL, json=["PING"], headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"}
            )
        except httpx2.HTTPError as exc:
            pytest.fail(
                f"no serverless-redis-http at {UPSTASH_URL} ({exc}). Start it with "
                "`docker compose up -d redis-http` from the repository root."
            )
    assert response.json() == {"result": "PONG"}, response.text


@pytest.fixture()
def shared_store(emulator: None) -> UpstashRateLimitStore:
    """The production adapter on the emulator, under a key prefix no other run uses.

    The prefix keeps a rerun inside the 60-second window from reading this run's hits."""
    return UpstashRateLimitStore(
        url=UPSTASH_URL, token=UPSTASH_TOKEN, key_prefix=f"test:{uuid.uuid4()}:"
    )


def _instance(monkeypatch: pytest.MonkeyPatch, store: RateLimitStore | None) -> FastAPI:
    """One app, as one Vercel instance builds it, counting in *store*, or in the store its
    settings select when *store* is None.

    Production's budget, read from the environment with nothing set, and without a
    developer's ``backend/.env``."""
    monkeypatch.delenv("RATE_LIMIT_AUTH_MAX_REQUESTS", raising=False)
    monkeypatch.setattr(main_module, "settings", Settings(_env_file=None))
    application = create_app(rate_limit_store=store)
    application.dependency_overrides[get_db] = _no_db
    return application


async def _burst(instances: list[FastAPI]) -> list[httpx2.Response]:
    """Send the burst concurrently, request *i* to instance ``i % len(instances)``."""
    clients = [
        AsyncClient(transport=ASGITransport(app=application), base_url="http://testserver")
        for application in instances
    ]
    try:
        return await asyncio.gather(
            *(clients[i % len(clients)].post("/api/v1/auth/login", json={}) for i in range(_BURST))
        )
    finally:
        for client in clients:
            await client.aclose()


async def test_two_instances_on_one_store_admit_the_budget_once_between_them(
    monkeypatch: pytest.MonkeyPatch, shared_store: UpstashRateLimitStore
) -> None:
    responses = await _burst(
        [_instance(monkeypatch, shared_store), _instance(monkeypatch, shared_store)]
    )

    assert Counter(r.status_code for r in responses) == {422: _BUDGET, 429: _BURST - _BUDGET}

    # A refusal from the shared store is the same refusal the in-memory one gives.
    refused = next(r for r in responses if r.status_code == 429)
    error = refused.json()["error"]
    assert error["code"] == "rate_limited"
    assert 1 <= error["detail"]["retry_after"] <= 61
    assert refused.headers["Retry-After"] == str(error["detail"]["retry_after"])


async def test_two_instances_select_the_shared_store_from_their_settings(
    monkeypatch: pytest.MonkeyPatch, emulator: None
) -> None:
    """The reading above with no store handed in: each app builds its own adapter from
    ``KV_REST_API_URL`` and ``KV_REST_API_TOKEN``, as a Vercel instance does, and the two
    still share one count. ``APP_ENV`` is in the key, so a fresh one isolates this run."""
    monkeypatch.setenv("KV_REST_API_URL", UPSTASH_URL)
    monkeypatch.setenv("KV_REST_API_TOKEN", UPSTASH_TOKEN)
    monkeypatch.setenv("APP_ENV", f"test-{uuid.uuid4().hex}")

    responses = await _burst([_instance(monkeypatch, None), _instance(monkeypatch, None)])

    assert Counter(r.status_code for r in responses) == {422: _BUDGET, 429: _BURST - _BUDGET}


async def test_negative_control_two_in_memory_stores_admit_the_budget_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What every Vercel instance did before #257: each counts only what it served."""
    responses = await _burst(
        [
            _instance(monkeypatch, InMemoryRateLimitStore()),
            _instance(monkeypatch, InMemoryRateLimitStore()),
        ]
    )

    assert Counter(r.status_code for r in responses) == {422: _BURST}


async def test_the_shared_store_refuses_at_the_budget_and_not_before(
    shared_store: UpstashRateLimitStore,
) -> None:
    """The adapter alone, in order, so the boundary is read request by request.

    The 21st is refused, a refusal is not recorded, and a hit leaves the window after it."""
    now = 1_000_000.0
    decisions = [
        await shared_store.hit("203.0.113.9", max_requests=_BUDGET, window_seconds=60, now=now + i)
        for i in range(_BUDGET + 2)
    ]

    assert [d.admitted for d in decisions] == [True] * _BUDGET + [False, False]
    # The oldest hit was at now + 0, so it leaves the window at now + 60. Asked at now + 20,
    # that is 40 seconds away, plus one.
    assert decisions[_BUDGET].retry_after == 41

    # At now + 60.5 the first hit has left and the second has not, so exactly one slot
    # frees. Had the two refusals been recorded, none would.
    later = now + 60.5
    assert (
        await shared_store.hit("203.0.113.9", max_requests=20, window_seconds=60, now=later)
    ).admitted
    assert not (
        await shared_store.hit("203.0.113.9", max_requests=20, window_seconds=60, now=later)
    ).admitted
