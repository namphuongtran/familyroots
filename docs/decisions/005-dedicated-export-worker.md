# ADR-005: Dedicated Worker Service for Heavy Exports

## Status
Accepted — **Deferred / not yet implemented** (as of 2026-07-16). No `worker`
service exists in the codebase, and it depends on ADR-004 (Redis), which is
also deferred. "Accepted" means agreed direction, not shipped. Note: lightweight
synchronous exports (JSON archive + GEDCOM) shipped separately via ADR-020
without a worker; this ADR remains the direction for heavy exports (PDF gia
phả book) only.

## Context
Generating PDF exports of large family trees is CPU and memory intensive. Running this in the main FastAPI event loop blocks standard API requests and degrades user experience.

## Decision
Create a dedicated `worker` service (Python-based) that listens to Redis queues to process heavy asynchronous tasks (e.g., PDF generation). The worker will upload results to Supabase Storage.

## Consequences
Easier:
- Backend API remains fast and responsive.
- Worker can be scaled independently of the API.

Harder:
- Clients must use polling, websockets, or push notifications to learn when the export is ready.
- Adds another service to deploy and monitor.