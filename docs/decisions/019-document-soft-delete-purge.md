# ADR-019: Document Soft-Delete + Retention Purge

## Status
Accepted (2026-07-12 — shipped). Supersedes the `documents` row of
[ADR-006](006-soft-vs-hard-delete.md)'s soft-vs-hard table: documents move from
hard-delete to soft-delete + retention purge.

## Context
The 2026-07-12 data-safety review found `document_repository.delete()`
hard-deleted the row and the command handler permanently removed the blob in
the same call — a misclick destroyed a scanned ancestral document
(certificate, photo) with no recovery path. `Document.mark_deleted()` and a
"reclaimable by a sweep" comment already existed in the codebase, but the
soft-delete columns didn't exist on the table and the sweep job didn't exist
either — the comment described a plan, not a behavior.

## Decision

### Schema (migration `016_document_soft_delete`)
Adds `is_deleted BOOLEAN NOT NULL DEFAULT false`, `deleted_at TIMESTAMPTZ`,
`deleted_by UUID` to `documents` (the same trio persons already carry), plus a
partial index `idx_documents_is_deleted ON documents (is_deleted) WHERE
is_deleted = false` for the live-only read path.

### Delete is soft
`DELETE /documents/{id}` (admin) calls the entity's `mark_deleted(actor)` and
saves — the row is flagged, `deleted_at`/`deleted_by` are stamped, and the blob
is **left untouched**. Reads and lists filter `is_deleted = false`, so a
soft-deleted document disappears from the UI immediately while its blob
remains downloadable (a presign against `storage_path` still succeeds) until
the purge job removes it.

### Restore
`POST /documents/{id}/restore` (admin) mirrors the persons restore semantics:
looks up via `get_deleted` (only matches a currently-soft-deleted row), 404s
if not found or not deleted, calls `restore(actor)`, and returns the full
`DocumentResponse` including a fresh presigned URL. Because the blob was never
removed, restore is a pure metadata flip with no storage round-trip.

### Retention purge job (`app/services/document_purge.py`)
A daily APScheduler job, `purge_expired_documents`, registered in
`app/services/scheduler.py` at `CronTrigger(hour=NOTIFICATION_CRON_HOUR,
minute=30)` — the same hour as the anniversary job, offset 30 minutes later so
the two never run concurrently on the same replica. It uses its own advisory
lock key `728_115_002` (distinct from the anniversary job's `728_115_001`) so
the two jobs never contend with each other, only with concurrent runs of
themselves — same lock topology as `send_anniversary_notifications` (dedicated
connection held for the whole job, working session bound to that connection,
rollback-before-unlock in `finally`).

The job selects `documents` rows where `is_deleted = true AND deleted_at <
now() - DOCUMENT_RETENTION_DAYS` (default 30, `Settings.DOCUMENT_RETENTION_DAYS`)
and, **per item**, executes three steps in this exact order — **claim row →
delete blob → commit**, the owner-adjudicated order for this PR (2026-07-12),
which supersedes an earlier blob-first draft of this ADR:

1. **Claim the row** inside the still-open transaction with a guarded
   `DELETE FROM documents WHERE id = :id AND is_deleted = true AND deleted_at <
   :cutoff`. Only a row that still matches the eligibility predicate at claim
   time is taken. If a restore landed between the batch `SELECT` snapshot and
   this claim, `rowcount == 0` — nothing was claimed, so the blob must not be
   touched; the item is rolled back and skipped.
2. **Delete the blob** — only once the row is claimed does `StoragePort.delete()`
   run.
3. **Commit** — only once the blob delete succeeds (returns `True` or raises,
   never silently swallowed) does the transaction commit.

**Crash analysis** (from the module docstring): this ordering means a crash or
exception anywhere in an item's processing rolls back the claim, so the row
survives to be retried on the next run — never a silent, partial purge.

- A blob that was actually deleted moments before a crash simply surfaces as
  "already gone" on the retry (the storage adapter's `delete()` contract
  treats confirmed-not-found as success — see below), so the row is purged
  cleanly next time; never a permanent orphan blob.
- A restore that races the sweep either lands before this row's claim
  (`rowcount == 0`, skip, blob and row both survive) or blocks on the claim's
  row lock and loses cleanly once the claim commits (the row is gone; the
  subsequent restore call 404s) — never a document silently destroyed out
  from under a user who just restored it.

Per-item error isolation: each item runs in its own `try`/`except`; a failure
(claim exception, storage exception, commit exception) is logged and rolled
back, and the sweep continues to the next row — one poisoned item can never
stop the whole purge run.

### Storage adapter `delete()` contract change
`StoragePort.delete()` (`app/domain/document/repository.py`) changed its
return-value contract to make the ordering above sound:

> Returns `True` when the object was deleted **or is confirmed already
> absent** (idempotent — a missing object is not a failure). Raises the
> appropriate `StorageError` subclass for transport/provider failures where
> deletion **could not be confirmed either way** — callers (notably the
> retention purge job, which commits its row-claim only after this call
> succeeds) must not treat a swallowed exception as "not found"; that would
> risk purging a row whose blob deletion is actually unconfirmed.

`SupabaseStorageAdapter.delete()` classifies the SDK exception:
`StorageNotFoundError` → `True` (confirmed not found, treated as success);
anything else re-raises the classified `StorageError`, which the purge job's
per-item `except` catches, logs, rolls back, and retries next run. This is a
stricter contract than the pre-PR1 delete flow (`docs/architecture/storage.md`'s
old ⚠️ banner), where "delete alone never raises" was safe only because it ran
post-commit as best-effort compensation with nothing depending on its return
value. Here the purge job's commit is gated on the return value, so
"unconfirmed" must surface as an exception, not a swallowed `False`/`True`.

### Avatar interplay (accepted)
Soft-deleting a document that is a person's avatar leaves the avatar URL
working until the purge job actually removes the blob — the blob is alive for
up to `DOCUMENT_RETENTION_DAYS` after a soft-delete, so `set_avatar`'s cached
presigned URL keeps resolving. This is an accepted v1 trade-off, not a bug: a
person's photo appearing to be "still their avatar" for up to 30 days after
an admin soft-deletes it is a much smaller failure than the avatar link
breaking immediately. No cross-aggregate cleanup (unsetting `is_avatar` on
soft-delete) was added in this pass.

### Deferred: orphan-blob reconciliation
Blobs with no matching row — left over from older compensation paths (e.g. a
pre-PR1 upload whose DB commit failed after the blob upload, per
`docs/architecture/storage.md`'s upload-flow compensation) — are **not**
reconciled by this job or any other in this PR. A reconciliation sweep needs
bucket-listing pagination (list every object under
`clans/{clan_id}/documents/` and diff against `documents.storage_path`), which
is a distinct capability from this row-driven purge. Tracked as a follow-up
ticket, not built here.

## Consequences
Easier: a misclicked document delete is now recoverable for a full
`DOCUMENT_RETENTION_DAYS` window via `POST /documents/{id}/restore`, matching
the recoverability persons already have (ADR-006). The purge job's
claim-first ordering means there is no code path that deletes a blob for a row
that isn't (still) eligible, and no code path that removes a row while its
blob deletion is unconfirmed.

Harder: documents now carry the same `is_deleted` query-filter burden as
persons/marriages/parent_child (every read must filter it — mirrors the
"mixed model" cost ADR-006 already accepted, now extended to one more
aggregate). A soft-deleted document's blob is billable storage for up to
`DOCUMENT_RETENTION_DAYS` days after delete, and its avatar linkage (if any)
keeps resolving during that window (accepted above). Orphan blobs from before
this PR (and from any future compensation-path failure) still require a
separate, not-yet-built reconciliation job — this ADR closes the "misclick
destroys history" gap, not the "storage bucket accumulates untracked blobs"
gap.

## Related
- [ADR-006](006-soft-vs-hard-delete.md) — selective soft-delete by aggregate;
  this ADR supersedes its `documents` row.
- [rest-documents-api.md](../contracts/rest-documents-api.md) — restore
  endpoint, retention window.
- [architecture/storage.md](../architecture/storage.md) — updated delete
  lifecycle and `StoragePort.delete()` contract.
- [architecture/notifications-scheduler.md](../architecture/notifications-scheduler.md)
  — `document_purge` job alongside the anniversary job.
- [ops/configuration.md](../ops/configuration.md) — `DOCUMENT_RETENTION_DAYS`.
