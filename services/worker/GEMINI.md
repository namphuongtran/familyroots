# worker

## Responsibility
Dedicated background service for heavy asynchronous tasks, such as PDF/Tree exports and processing large image uploads. It offloads long-running tasks from the main FastAPI backend.

## Stack
Python, Redis (Pub/Sub or queues), APScheduler / Celery / RQ (TBD)

## Domain Model
Task definitions and status payloads.

## API Surface
None (Internal service driven by message queues).

## Event Contracts
Consumes: Export tasks, heavy processing jobs via Redis from `backend`.
Publishes: Status updates or file-ready notifications via Redis to `backend`.

## Data Ownership
No database ownership. Uploads generated artifacts to Supabase Storage.

## Key Commands
<!-- TODO: define worker run commands -->

## Error Handling Pattern
Task retries with exponential backoff. Failed tasks sent to Sentry and marked as failed in the DB via API/direct DB update.

## Don't Do
- Do not serve HTTP traffic.
- Do not perform synchronous blocking operations without acknowledging the message.

## Known Issues
- Just scaffolded; implementation pending.