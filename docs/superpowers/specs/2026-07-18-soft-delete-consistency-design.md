# Soft-Delete Consistency Sweep (A5) — Design

**Date:** 2026-07-18
**Source findings:** M3 in `docs/architecture/backend-review-2026-07-18.md`
(write guards ignore `Person.is_deleted`; `/events/upcoming` leaks deleted
persons' giỗ), plus two additional unguarded sites found by this design's own
sweep (documents, branches).

## Problem — the "invisible person" contract has holes

The read surfaces treat a soft-deleted person as invisible (persons list/get,
tree, search, timeline — all filter `is_deleted`), and the relationship
validator's own docstring states the rule ("a person outside your clan is
invisible to you"). But five write/read paths never check it:

1. `relationship_repository.persons_in_clan` (:364) — marriages and
   parent-child edges can be CREATED for a soft-deleted person. Restore then
   surprises the clan with edges/spouse_order slots that shifted invisibly.
2. `event_repository.person_in_clan` (:47) — events (giỗ!) can be created for
   a soft-deleted person.
3. `document_repository.person_in_clan` (:89) — documents can be attached to a
   soft-deleted person (found by this sweep, same class).
4. `branch_repository.person_in_clan` (:34) — branch assignment paths accept a
   soft-deleted person (found by this sweep; verify the exact caller semantics
   during implementation and pin whatever operation it guards).
5. `relationship_repository.get_birth_dates` (:357) — no `is_deleted` filter;
   moot for creates once (1) lands, but fixed for consistency (the
   `parent_too_young` check must never reason from an invisible person's data).

And one read leak:

6. `/events/upcoming` (`event_repository.get_upcoming`, solar CTE ~:110 and
   lunar query ~:137): both `LEFT JOIN persons p` with **no
   `p.is_deleted = false` predicate** — a deleted person's recurring giỗ still
   appears, WITH their name, while the scheduler correctly suppresses the same
   event (`scheduler.py` filters `person_id IS NULL OR p.is_deleted = false`).
   Clients show a giỗ that will never be notified, and the deleted person's
   name leaks through the one remaining unfiltered join.

## Design — enforce the documented semantics, no new contract

- **Guards 1–4**: each `person_in_clan`/`persons_in_clan` gains
  `JOIN persons ... AND persons.is_deleted = false` (exactly the pattern
  A3's `clan_repository.get_membership_with_person` already uses). The failing
  guard keeps producing each caller's EXISTING error (404 `person_not_found` /
  the validator's clan-invisible 4xx — verify per call site, change no codes).
  A soft-deleted person on a write path now behaves identically to a
  non-member: invisible.
- **Guard 5**: `get_birth_dates` adds `PersonModel.is_deleted.is_(False)` —
  a deleted person's birth date simply doesn't participate.
- **Leak 6**: both upcoming queries gain the scheduler's exact predicate
  `(e.person_id IS NULL OR p.is_deleted = false)` — person-less events
  (custom/clan ceremonies) keep flowing; person-bound events of deleted
  persons disappear from `/events/upcoming`, matching the scheduler
  ("upcoming shows what will actually be notified").
- **Restore symmetry**: restoring the person makes all of the above work
  again with zero further action (filters are live-state predicates) — pinned
  by tests, not new code.
- **Events already attached to a person who is LATER soft-deleted** keep
  existing (ADR-022 semantics untouched); they are merely invisible in
  `/upcoming` and un-notified while the person is deleted.

## Explicitly out of scope

- Cascade-soft-delete of edges/events when a person is deleted (roadmap E3,
  tracked; this PR only stops NEW attachments and the read leak).
- The events `person_id` FK SET NULL semantics (ADR-022).
- Any error-code or contract-shape change: `docs/contracts` needs at most a
  behavior-note sync (grep sweep decides), no ADR (this enforces an already-
  documented rule; cite M3).

## Tests (real-DB; RED-first)

1. For EACH of marriages, parent-child, events, documents, branch-op: create
   targeting a soft-deleted person over the real handler/HTTP path → the
   caller's existing invisible-person error; positive control (live person →
   2xx); **restore → the same call succeeds** (symmetry).
2. `/events/upcoming`: seed a recurring giỗ for person X + one for live Y +
   one person-less clan event → soft-delete X → upcoming shows Y's and the
   person-less event, X's absent, X's name nowhere in the payload; scheduler
   parity asserted (the two surfaces agree). Restore X → giỗ reappears.
3. `get_birth_dates` unit-level pin: deleted person excluded from the map.
4. Sweep completeness gate: a test (or reviewed grep evidence in the PR) that
   every `person_in_clan`-style guard in `app/infrastructure/persistence`
   filters `is_deleted` — so the next aggregate's author can't reintroduce the
   class. (Implement as a source-scan test over the repository modules if a
   robust runtime enumeration isn't practical; decide in the plan.)
