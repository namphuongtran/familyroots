"""The image's HEALTHCHECK probe, read against a real server behind the real host check (#230).

The outcome is the probe's exit status against ``TrustedHostMiddleware`` holding a given
``ALLOWED_HOSTS``, the middleware ``create_app`` installs. Which Host the probe picks is a setting,
and asserting it alone would pass for a name the middleware refuses. So each case starts uvicorn,
sends the probe's real request over a socket, and reads whether the probe reports healthy.

Starlette matches a ``*.domain`` pattern by suffix, so it also admits the literal pattern, and
``*`` admits anything, ``*`` included. Neither is a host name a proxy or a log would accept, so the
server also records the Host it received, and each case requires that to be a DNS name.
"""

from __future__ import annotations

import re
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app import healthcheck
from app.core.config import Settings

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
            threading.Event().wait(0.01)
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
    "one exact host, as Render's blueprint set": ["familyroots-api.onrender.com"],
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


def test_main_reads_the_list_the_app_hands_the_middleware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main`` takes its Host from ``Settings.trusted_hosts``, the list ``create_app`` passes to
    ``TrustedHostMiddleware``, read from the environment the way the app reads it."""
    monkeypatch.setenv("ALLOWED_HOSTS", '["127.0.0.1"]')
    monkeypatch.setattr(healthcheck, "get_settings", lambda: Settings(_env_file=None))
    with _serving(["127.0.0.1"]) as (port, _):
        monkeypatch.setattr(healthcheck, "PORT", port)
        assert healthcheck.main() == 0
    monkeypatch.setenv("ALLOWED_HOSTS", "[]")
    assert healthcheck.main() == 1
