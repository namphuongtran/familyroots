# ADR-014: Unit of Work Dispatches Domain Events In-Transaction (Audit Guarantee)

## Status
Accepted (shipped; supersedes nothing — refines ADR-001, coexists with deferred ADR-004)

## Context
Every mutation must produce an audit row (actor, action, old/new values). If audit
writes happened after commit (or in another process), a crash window could leave
mutations without audit — unacceptable for a genealogy system whose core promise is
traceable edits.

## Decision
`SqlAlchemyUnitOfWork.commit()` runs: flush → collect domain events from tracked
aggregates → **dispatch handlers inline (same transaction)** → commit. The
`AuditLogHandler` therefore writes audit rows atomically with the mutation: a failing
handler rolls the whole write back. Aggregates are tracked at the repository seam
(`save()`/`delete()` call `uow.track()`), so handlers can't forget.

Corollary (the "Never Do" rule): these events are **process-local and not durable**
— they must not be treated as integration events. Cross-service delivery needs the
deferred Redis/outbox design (ADR-004) with explicit mitigation.

## Consequences
Easier: audit is guaranteed-atomic; new side-effects subscribe without touching
handlers; tests can assert audit rows in the same transaction.
Harder: event handlers run on the write path (latency + failure coupling — a buggy
subscriber blocks writes); no retry/durability semantics; anything requiring
guaranteed async delivery is out of scope until an outbox exists.
