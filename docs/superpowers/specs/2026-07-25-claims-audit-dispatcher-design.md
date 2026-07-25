# Claims Audit → Fail-Closed Dispatcher (M12) — Design

**Date:** 2026-07-25
**Source finding:** M12 in `docs/architecture/backend-review-2026-07-18.md`.

## Problem

Every other write module routes audit through the **sanctioned fail-closed
dispatcher** (`emit_audit_event` → `AuditLogHandler`), which (a) writes the
`AuditLog` row in the same transaction and aborts the whole write if the audit
fails, and (b) enriches `ip_address`/`user_agent` from the `RequestMeta`
ContextVar. The claims aggregate does NOT:

- `claim_repository.add_audit` (`app/infrastructure/persistence/claim_repository.py:130-140`)
  builds `AuditLog(...)` directly via `session.add` — **bypassing the
  dispatcher**, so all six claim audit rows (submit/approve/reject/unlink/
  prelink/cancel) permanently lack `ip_address`/`user_agent`.
- `cancel_claim` (`app/application/person/claim_handlers.py:90-101`) writes its
  audit only `if person:` — a cancel whose person row can't be fetched commits
  the state change with **no audit row at all**, violating the fail-closed
  intent.

## Design (no migration, no new ADR — makes claims consistent with the sanctioned pattern)

### 1. A commit-free tracked-audit helper

`emit_audit_event` commits internally, but the claim handlers each do their own
`await self._uow.commit()` after the state change — calling `emit_audit_event`
would double-commit. Extract the aggregate-and-track step:

```python
# app/application/shared/audit.py
def track_audit_event(uow, *, action, resource_type, resource_id, actor, clan_id,
                      old_value=None, new_value=None) -> None:
    """Buffer a CrudAuditEvent on a tracked aggregate WITHOUT committing — the
    caller commits (and thus dispatches it) as part of its own write transaction.
    Routes through the fail-closed AuditLogHandler (same-txn + ip/UA enrichment)."""
    agg = AggregateRoot()
    agg.add_event(CrudAuditEvent(action=..., resource_type=..., resource_id=...,
                                 clan_id=clan_id, actor_id=actor.user_id,
                                 actor_role=actor.role, old_value=old_value,
                                 new_value=new_value))
    uow.track(agg)
```

`emit_audit_event` is refactored to call `track_audit_event` then `await uow.commit()`
(behavior identical for its existing callers — documents, auth).

### 2. Migrate all six claim audit sites

Replace each `self._repo.add_audit(...)` in `claim_handlers.py` (submit, cancel,
approve, reject, unlink, prelink) with `track_audit_event(self._uow, ...)`,
preserving each site's exact `action` / `resource_type` / `resource_id` /
`old_value` / `new_value` / actor. The existing per-handler `await
self._uow.commit()` then dispatches it through the fail-closed handler — same
transaction as the claim state change, now with ip/UA enrichment. The claim
handlers construct an `ActorInfo(user_id, role)` from the ids/roles they already
pass to `add_audit`.

### 3. cancel_claim: audit unconditionally

`cancel_claim` loads the person only to obtain `clan_id`. Since `AuditLog.clan_id`
is **nullable**, drop the `if person:` skip: always track the audit, with
`clan_id = person.created_by_clan_id if person else None`. The audit row now
always lands (fail-closed intent restored) even in the theoretical case the
person can't be fetched.

### 4. Remove the dead direct-writer

`claim_repository.add_audit` becomes unused after the migration — delete it (and
its now-unused `AuditLog` import if nothing else in the module uses it). This
also removes the last non-dispatcher audit writer, so no module can silently
drift again (the review's stated goal).

## What does NOT change

- The claims API, response shapes, error codes.
- What each claim action audits (action names, old/new values) — only the WRITE
  PATH changes (direct → dispatcher).
- The claims domain `ClaimEntity` — we use the generic `CrudAuditEvent` (as
  documents/events/branches/auth do), not new per-claim domain events; claims
  audit is CRUD-style, so this is the consistent, minimal choice.

## Tests (real-DB; RED-first)

1. **ip/UA enrichment** (the concrete, testable bug): drive a claim action over
   HTTP (real request → `RequestMetaMiddleware` populates the ContextVar) — e.g.
   `POST /persons/{id}/claim` — then read the resulting `audit_logs` row: its
   `ip_address` / `user_agent` are POPULATED (RED today: NULL, because claims
   bypass the enriching dispatcher). Cover submit + one admin action
   (approve/reject) + cancel.
2. **cancel always audits**: cancelling a pending claim writes exactly one
   `claim.cancel` audit row (proves the path audits; the `if person:` removal is
   a code simplification — the person-None case is unreachable via the FK, so it
   is documented, not separately seedable).
3. **Audit content preserved**: the migrated sites still write the same
   `action` / `resource_type` / `resource_id` / old/new values (pin one
   representative action's row shape).
4. Existing claims + audit suites stay green (the rows still exist, now enriched).

## Docs

- `docs/architecture/backend-developer-guide.md` (or the audit section): claims
  now route through the fail-closed dispatcher; `add_audit` retired — the
  dispatcher (`emit_audit_event` / `track_audit_event`) is the ONLY audit writer.
- Grep sweep: `add_audit|audit|claim` across docs/contracts + docs/architecture;
  per-hit dispositions.

## Addendum (discovered during Task 1): approve/reject 500 post-commit — folded into M12

`approve_claim` / `reject_claim` end with `return IdentityClaimResponse.model_validate(claim)`
AFTER `uow.commit()`. `IdentityClaimResponse` declares `updated_at`, whose column
carries `onupdate=func.now()` (server-side). After the status UPDATE, SQLAlchemy
expires `updated_at` (it can't know the server-computed value and does not RETURNING
it on UPDATE), so `model_validate` accessing it triggers an **async lazy refresh
outside a greenlet → MissingGreenlet**, wrapped as a pydantic ValidationError → the
handler 500s **even though the commit succeeded** (the claim IS approved/rejected).
`submit_claim` is unaffected (INSERT fetches server defaults via RETURNING); `cancel`
returns None (no serialization).

This is a real, user-facing pre-existing bug (mislabeled a "test-harness artifact" in
`tests/integration/test_claim_approval.py`). M12's own approve/reject audit tests
can't cleanly assert a 200 without it, and M12 already rewrites these handlers, so
the fix is folded in: after commit, before `model_validate`, refresh the expired
timestamp columns within the async context —
`await self._uow.session.refresh(claim, attribute_names=["updated_at", "created_at"])`
— on both `approve_claim` and `reject_claim`. Both this suite's approve-tolerance and
the pre-existing `test_claim_approval.py` tolerance are removed to assert clean 200s.
