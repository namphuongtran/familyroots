"""`SCHEDULER_ENABLED` decides whether the lifespan runs the in-process APScheduler (ADR-065).

Runs the real ``lifespan`` from ``app.main`` and reads the scheduler's own ``running`` state
inside it and after it. Everything the lifespan touches besides the scheduler is stubbed:
the database readiness checks, Firebase, translations, logging, and the engine dispose. No
database or network is needed.

With the setting false, two things must hold. APScheduler never starts, because on Vercel
an instance is frozen between requests and the timer could only misfire. And shutdown does
not try to stop a scheduler that never started, which would log an exception from
``_safe("scheduler-stop", ...)`` at every cold instance's teardown.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from fastapi import FastAPI

import app.main as main_module
from app.core.config import settings
from app.core.readiness import MIGRATIONS_CURRENT
from app.services.scheduler import scheduler

pytestmark = pytest.mark.unit


class _NoDbSession:
    async def __aenter__(self) -> _NoDbSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _NoDbEngine:
    async def dispose(self) -> None:
        return None


@pytest.fixture
def isolated_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    async def migrations_are_current(_session: Any) -> str:
        return MIGRATIONS_CURRENT

    monkeypatch.setattr(main_module, "migration_status", migrations_are_current)
    monkeypatch.setattr(main_module, "AsyncSessionLocal", _NoDbSession)
    monkeypatch.setattr(main_module, "init_firebase", lambda: None)
    monkeypatch.setattr(main_module, "load_translations", lambda: None)
    # configure_logging clears the root handlers, which would take caplog's with them.
    monkeypatch.setattr(main_module, "configure_logging", lambda: None)
    monkeypatch.setattr("app.core.database.engine", _NoDbEngine())
    monkeypatch.setattr(settings, "RLS_ENABLED", False)
    monkeypatch.setattr(settings, "SENTRY_DSN", "")


async def test_enabled_runs_apscheduler_for_the_life_of_the_app(
    isolated_lifespan: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", True)
    assert not scheduler.running

    async with main_module.lifespan(FastAPI()):
        assert scheduler.running
        assert {job.id for job in scheduler.get_jobs()} == {
            "anniversary_notifications",
            "document_purge",
        }
    await asyncio.sleep(0)  # let the loop run the shutdown callback

    assert not scheduler.running


async def test_disabled_never_starts_apscheduler_and_never_tries_to_stop_it(
    isolated_lifespan: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", False)
    assert not scheduler.running

    with caplog.at_level(logging.ERROR, logger="app.main"):
        async with main_module.lifespan(FastAPI()):
            assert not scheduler.running
        await asyncio.sleep(0)

    assert not scheduler.running
    failures = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert failures == [], failures


def test_the_default_keeps_the_in_process_scheduler() -> None:
    """Local and Docker set nothing and must keep today's behaviour."""
    from app.core.config import Settings

    assert Settings(_env_file=None).SCHEDULER_ENABLED is True
