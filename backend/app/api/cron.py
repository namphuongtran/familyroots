"""Vercel Cron's way into the two scheduled jobs (ADR-065).

On Vercel Functions an instance is frozen between requests, so the in-process APScheduler
(``app/services/scheduler.py``) never fires there. ``SCHEDULER_ENABLED=false`` keeps it off,
and Vercel Cron sends ``GET`` to these two routes on a schedule instead. Each runs the
existing job unchanged. The job's transaction-scoped advisory lock makes a concurrent
delivery skip, and its own dedup or eligibility check makes a repeated one a no-op. Vercel's
cron docs, read 2026-10-10: "Cron delivery can also occasionally invoke the same scheduled
run more than once."

**Authentication** is ``Authorization: Bearer <CRON_SECRET>``, which is the header Vercel
Cron sends, compared as bytes in constant time. **Every failure is the same bare 404** that
``/internal/metrics`` gives, and that a path which does not exist gives (ADR-021, ADR-040).
That covers no header, a wrong secret, and a ``CRON_SECRET`` that is empty or below the
``metrics_token_weakness`` floor. A scanner must not learn that these routes exist.

**Success is 204 with no body.** The job reports in the logs. Vercel reads only the status,
and a 204 sits inside the frozen envelope rather than needing an exemption from it. A
job-fatal error propagates and answers 500. Hidden from the OpenAPI schema, and excluded
from the Prometheus instrumentator in ``create_app``.
"""

import secrets

from fastapi import APIRouter, Depends, Request, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import metrics_token_weakness, settings
from app.services import document_purge, scheduler

ANNIVERSARY_NOTIFICATIONS_PATH = "/internal/cron/anniversary-notifications"
DOCUMENT_PURGE_PATH = "/internal/cron/document-purge"


def require_cron_secret(request: Request) -> None:
    """Admit only ``Authorization: Bearer <CRON_SECRET>``. Otherwise raise the bare 404.

    The configured secret is re-checked against the floor on every request, the way
    ``/internal/metrics`` re-checks ``METRICS_TOKEN``. Settings validation enforces the
    floor only in production with the scheduler off, so this is what keeps a weak secret
    from opening the routes anywhere else, and what fails closed if validation was
    bypassed.

    Both sides are compared as the exact wire bytes. Starlette decodes header bytes as
    latin-1, so ``.encode("latin-1")`` restores them, and a non-ASCII header cannot raise
    and answer 500 where a missing route answers 404. ``os.environ`` decodes with
    surrogateescape, so ``.encode("utf-8", "surrogateescape")`` restores the configured
    bytes and cannot raise either (see ``internal_metrics`` in ``app/main.py``).
    """
    not_found = StarletteHTTPException(status_code=404)
    secret = settings.CRON_SECRET
    if metrics_token_weakness(secret):
        raise not_found
    presented = request.headers.get("Authorization")
    if presented is None or not secrets.compare_digest(
        presented.encode("latin-1"),
        f"Bearer {secret}".encode("utf-8", "surrogateescape"),
    ):
        raise not_found


cron_router = APIRouter(include_in_schema=False, dependencies=[Depends(require_cron_secret)])


@cron_router.get(ANNIVERSARY_NOTIFICATIONS_PATH, status_code=204)
async def run_anniversary_notifications() -> Response:
    """Run the daily giỗ/anniversary push job once (``send_anniversary_notifications``)."""
    await scheduler.send_anniversary_notifications()
    return Response(status_code=204)


@cron_router.get(DOCUMENT_PURGE_PATH, status_code=204)
async def run_document_purge() -> Response:
    """Run the ADR-019 retention purge once (``purge_expired_documents``)."""
    await document_purge.purge_expired_documents()
    return Response(status_code=204)
