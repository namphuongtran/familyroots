"""The rate limit's count in Upstash Redis, shared by every instance (ADR-072).

On Vercel Functions the backend runs as many short-lived instances, so a count kept in
process memory holds per instance (ADR-065 § 7). This adapter keeps the sliding log of one
key in a Redis sorted set, scored by the hit's wall-clock time, and reaches it through
Upstash's REST API: one ``POST`` per counted request, carrying one ``EVAL``.

The check and the record are one Lua script, so they are one atomic step in Redis. Two
instances deciding at the same moment cannot both take the last slot.
"""

from __future__ import annotations

import asyncio
import secrets

import httpx2

from app.core.rate_limit import (
    RateDecision,
    RateLimitStoreUnavailableError,
    retry_after_seconds,
)

# How long one decision may take before the request is decided in memory instead. Upstash
# answers an EVAL in a few milliseconds from the same region (`ap-southeast-1`, beside
# Vercel's `sin1`), and a cold instance's first call adds a TLS handshake. Half a second is
# many times both, and it is the most a sign-in waits when the store is down (ADR-072).
DEFAULT_TIMEOUT_SECONDS = 0.5

# KEYS[1] the log. ARGV: now, the cutoff (now - window), the budget, a member unique to this
# hit, and the key's time to live in milliseconds. Scores travel as strings both ways, so
# Lua never formats a float. A hit is in the window while its score is above the cutoff,
# which is the in-memory store's rule (`t > cutoff`).
_SLIDING_LOG = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[2])
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  return {0, oldest[2]}
end
redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
redis.call('PEXPIRE', KEYS[1], ARGV[5])
return {1}
"""


class UpstashRateLimitStore:
    """A ``RateLimitStore`` in Upstash Redis.

    Args:
        url: The database's REST URL, ``KV_REST_API_URL`` as the Vercel integration names it.
        token: Its read-write REST token, ``KV_REST_API_TOKEN``.
        key_prefix: Prepended to every key, so two deployments sharing one database, such as
            Production and Development, never share a count.
        timeout_seconds: The whole decision's deadline, connection included.
        transport: Replaces the network, for tests.
    """

    def __init__(
        self,
        *,
        url: str,
        token: str,
        key_prefix: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._prefix = key_prefix
        self._timeout = timeout_seconds
        self._transport = transport
        # One client per event loop, so a burst reuses its connection. A client is bound to
        # the loop that opened its connections, and tests run one loop per test. The client
        # has no timeout of its own: the deadline in hit() covers the whole call, connection
        # included, where httpx2 would time each phase separately.
        self._client: httpx2.AsyncClient | None = None
        self._client_loop: asyncio.AbstractEventLoop | None = None

    def _client_for_this_loop(self) -> httpx2.AsyncClient:
        loop = asyncio.get_running_loop()
        if self._client is None or self._client_loop is not loop:
            self._client = httpx2.AsyncClient(timeout=None, transport=self._transport)
            self._client_loop = loop
        return self._client

    async def hit(
        self, key: str, *, max_requests: int, window_seconds: int, now: float
    ) -> RateDecision:
        cutoff = now - window_seconds
        command = [
            "EVAL",
            _SLIDING_LOG,
            "1",
            f"{self._prefix}{key}",
            repr(now),
            repr(cutoff),
            str(max_requests),
            f"{now!r}:{secrets.token_hex(8)}",
            str(window_seconds * 1000),
        ]
        try:
            async with asyncio.timeout(self._timeout):
                response = await self._client_for_this_loop().post(
                    self._url, json=command, headers=self._headers
                )
            body = response.json()
            if response.status_code != 200 or "error" in body:
                raise RateLimitStoreUnavailableError(
                    f"HTTP {response.status_code}: {body.get('error', 'no error given')}"
                )
            result = body["result"]
            if int(result[0]) == 1:
                return RateDecision(admitted=True)
            return RateDecision(
                admitted=False, retry_after=retry_after_seconds(float(result[1]), cutoff)
            )
        except RateLimitStoreUnavailableError:
            raise
        except TimeoutError as exc:
            raise RateLimitStoreUnavailableError(
                f"no answer within {self._timeout} seconds"
            ) from exc
        except Exception as exc:
            # Anything else the call raises: a transport failure, a URL httpx2 cannot parse
            # (InvalidURL is not an HTTPError), a body that is not JSON, or JSON of another
            # shape. Broad on purpose, because whatever escapes here answers sign-in with a 500.
            raise RateLimitStoreUnavailableError(f"{type(exc).__name__}: {exc}") from exc
