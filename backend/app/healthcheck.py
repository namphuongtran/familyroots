"""The backend image's HEALTHCHECK: ``python -m app.healthcheck`` (#230).

It sends ``GET /health`` to this container and exits 0 only on a 200. ``TrustedHostMiddleware``
answers 400 to a Host outside ``ALLOWED_HOSTS``, and a production list never names ``localhost``,
so the probe sends a Host the app itself admits. It reads that list through the same ``Settings``
the app builds, from the container's own environment, so nothing here or in the Dockerfile types
a host name.

``/health`` reads the database (``app/main.py``), so the probe still exits 1 when nothing is
listening, when the database is unreachable, or when migrations are behind.
"""

from __future__ import annotations

import http.client
import sys
from collections.abc import Sequence

from app.core.config import get_settings

# backend/Dockerfile's CMD binds uvicorn to this port.
PORT = 8000
# Under the HEALTHCHECK's --timeout=5s, so a hung request is reported by the probe, not killed.
TIMEOUT_SECONDS = 4.0
# The label sent under a ``*.domain`` wildcard. The middleware admits any name under the domain.
_WILDCARD_LABEL = "healthcheck"


def probe_host(allowed_hosts: Sequence[str]) -> str | None:
    """A Host header ``TrustedHostMiddleware`` admits under *allowed_hosts*.

    ``None`` when the list is empty: the middleware then admits no host at all."""
    if not allowed_hosts:
        return None
    first = allowed_hosts[0]
    if first == "*":
        return "localhost"
    if first.startswith("*."):
        return _WILDCARD_LABEL + first[1:]
    return first


def probe(host: str, port: int) -> int:
    """``GET /health`` on this machine's *port* with ``Host: host``. 0 on a 200, else 1."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=TIMEOUT_SECONDS)
    try:
        connection.request("GET", "/health", headers={"Host": host})
        response = connection.getresponse()
        body = response.read(200).decode("utf-8", "replace")
    except (OSError, http.client.HTTPException) as exc:
        print(f"GET /health (Host: {host}) failed: {exc!r}")
        return 1
    finally:
        connection.close()
    print(f"GET /health (Host: {host}) -> {response.status} {body}")
    return 0 if response.status == 200 else 1


def admitted_host() -> str | None:
    """A Host this app admits, from ``Settings.trusted_hosts``: the list ``create_app`` hands
    ``TrustedHostMiddleware``, read from this process's environment."""
    return probe_host(get_settings().trusted_hosts)


def main(port: int = PORT) -> int:
    host = admitted_host()
    if host is None:
        print("ALLOWED_HOSTS is empty, so TrustedHostMiddleware admits no request to /health")
        return 1
    return probe(host, port)


if __name__ == "__main__":
    sys.exit(main())
