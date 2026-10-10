"""The image's HEALTHCHECK probe, read against a real server behind the real host check (#230).

The outcome is the probe's exit status against Starlette's ``TrustedHostMiddleware``, the class
``create_app`` installs, holding a given ``ALLOWED_HOSTS``. Which Host the probe picks is a setting,
and asserting it alone would pass for a name the middleware refuses. So each case starts uvicorn,
sends the probe's real request over a socket, and reads whether the probe reports healthy. The
cases headed "the real app" then build ``create_app`` itself, as
``test_trusted_hosts_vercel_url.py`` does, and read its answer to the Host the probe chose, so the
probe cannot drift from the list the app really hands its middleware.

Starlette matches a ``*.domain`` pattern by suffix, so it also admits the literal pattern, and
``*`` admits anything, ``*`` included. Neither is a host name a proxy or a log would accept, so the
server also records the Host it received, and each case requires that to be a DNS name.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
import uvicorn
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

import app.main as main_module
from app import healthcheck
from app.core.config import Settings, get_settings

pytestmark = pytest.mark.unit


_DNS_NAME = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))*$")


@contextmanager
def _serving(allowed_hosts: list[str], health_status: int = 200) -> Iterator[tuple[int, list[str]]]:
    """Serve ``GET /health`` behind ``TrustedHostMiddleware`` on a free port.

    Yields the port, and the Host of each request the middleware let through."""
    received: list[str] = []

    async def health(request: Request) -> JSONResponse:
        received.append(request.headers["host"])
        return JSONResponse({"status": "ok"}, status_code=health_status)

    app = Starlette(
        routes=[Route("/health", health)],
        middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)],
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, lifespan="off", log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(500):
            if server.started:
                break
            time.sleep(0.01)
        assert server.started, "uvicorn did not start within 5 s"
        yield server.servers[0].sockets[0].getsockname()[1], received
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _closed_port() -> int:
    """A port nothing listens on: bound once to learn a free number, then released."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


# Every shape the production validator admits, plus the development default.
_ALLOWED_HOSTS_SHAPES = {
    "one exact host, the shape Render's blueprint set": ["familyroots-api.onrender.com"],
    "one exact address, as image-e2e.yml sets": ["127.0.0.1"],
    "several hosts": ["api.familyroots.example", "familyroots-api.vercel.app"],
    "a *.domain wildcard first": ["*.familyroots.example", "familyroots-api.vercel.app"],
    "the development default": ["*"],
}


@pytest.mark.parametrize(
    "allowed_hosts", _ALLOWED_HOSTS_SHAPES.values(), ids=_ALLOWED_HOSTS_SHAPES.keys()
)
def test_the_probe_reports_healthy_under_each_allowed_hosts_shape(
    allowed_hosts: list[str],
) -> None:
    host = healthcheck.probe_host(allowed_hosts)
    assert host is not None
    with _serving(allowed_hosts) as (port, received):
        assert healthcheck.probe(host, port) == 0
    assert len(received) == 1
    assert _DNS_NAME.match(received[0]), f"the server received Host {received[0]!r}"


def test_the_old_probes_localhost_is_refused_where_the_new_host_is_admitted() -> None:
    """The failing reading differs from the passing one: the same server, two Host headers.

    ``localhost`` is what the probe sent before #230, and a production list never names it."""
    with _serving(["127.0.0.1"]) as (port, _):
        assert healthcheck.probe("localhost", port) == 1
        assert healthcheck.probe("127.0.0.1", port) == 0


def test_the_probe_reports_unhealthy_when_health_does_not_answer_200() -> None:
    """``/health`` answers 503 when the database is unreachable or behind (app/main.py)."""
    with _serving(["127.0.0.1"], health_status=503) as (port, _):
        assert healthcheck.probe("127.0.0.1", port) == 1


def test_the_probe_reports_unhealthy_when_nothing_is_listening() -> None:
    assert healthcheck.probe("127.0.0.1", _closed_port()) == 1


def test_an_empty_allowed_hosts_admits_no_host_so_the_probe_has_none_to_send() -> None:
    """The validator refuses only ``["*"]``, so ``[]`` boots, and the middleware admits nothing."""
    assert healthcheck.probe_host([]) is None


@pytest.fixture()
def app_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """The one ``Settings`` both the probe and ``create_app`` read, as in a running container.

    ``tests/integration/conftest.py`` replaces ``get_settings()``'s instance mid-run, which leaves
    ``app.main``'s import-time binding on the old one, so a full run would split them."""
    current = get_settings()
    monkeypatch.setattr(main_module, "settings", current)
    return current


def _real_app_answer(host: str) -> int:
    """The status ``create_app`` answers for *host* on a path no route serves: the route's 404
    when ``TrustedHostMiddleware`` admits the host, its bare 400 when it does not."""
    client = TestClient(main_module.create_app(), base_url=f"http://{host}")
    return client.get("/internal/no-such-route").status_code


@pytest.mark.parametrize(
    "allowed_hosts", _ALLOWED_HOSTS_SHAPES.values(), ids=_ALLOWED_HOSTS_SHAPES.keys()
)
def test_the_real_app_admits_the_host_the_probe_takes_from_its_settings(
    monkeypatch: pytest.MonkeyPatch, app_settings: Settings, allowed_hosts: list[str]
) -> None:
    monkeypatch.setattr(app_settings, "ALLOWED_HOSTS", allowed_hosts)
    monkeypatch.setattr(app_settings, "VERCEL_URL", "")
    host = healthcheck.admitted_host()
    assert host is not None
    assert _real_app_answer(host) == 404
    # The control this case exists for: the real app refuses the old probe's Host.
    if "*" not in allowed_hosts:
        assert _real_app_answer("localhost") == 400


def test_the_real_app_admits_the_probes_host_when_only_vercel_url_names_one(
    monkeypatch: pytest.MonkeyPatch, app_settings: Settings
) -> None:
    """``trusted_hosts``, not ``ALLOWED_HOSTS``: the one shape where the two lists differ."""
    monkeypatch.setattr(app_settings, "ALLOWED_HOSTS", [])
    monkeypatch.setattr(app_settings, "VERCEL_URL", "familyroots-9xtnrccz1-namtp.vercel.app")
    host = healthcheck.admitted_host()
    assert host is not None
    assert _real_app_answer(host) == 404


def test_main_probes_under_the_host_from_its_settings(
    monkeypatch: pytest.MonkeyPatch, app_settings: Settings
) -> None:
    monkeypatch.setattr(app_settings, "ALLOWED_HOSTS", ["127.0.0.1"])
    monkeypatch.setattr(app_settings, "VERCEL_URL", "")
    with _serving(["127.0.0.1"]) as (port, received):
        assert healthcheck.main(port) == 0
        monkeypatch.setattr(app_settings, "ALLOWED_HOSTS", [])
        assert healthcheck.main(port) == 1
    assert received == ["127.0.0.1"]
