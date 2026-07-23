# Thủy Tổ (Founder) Designation (A3) — Design

**Date:** 2026-07-18
**Source finding:** H3 in `docs/architecture/backend-review-2026-07-18.md` —
`is_founder` is unreachable dead code on the write side: `PersonCreateRequest`
exposes no such field, no membership-update endpoint exists, so for every
API-managed clan `find_clan_founder` returns nothing, `GET /tree` 404s
`clan_founder_not_found`, every đời is null, and GEDCOM emits no đời notes.
The flagship graph-computed đời feature cannot activate. Also: `find_clan_founder`
is `LIMIT 1` with **no ORDER BY** (nondeterministic root on multi-founder data).
**Owner decision:** one founder + swap endpoint (over founder-set management and
over exposing `is_founder` on person create).

## Design

### 1. New admin endpoint — designate or correct in one idempotent operation

```
PUT /api/v1/clans/me/founder
Body: {"person_id": "<uuid>"}
Auth: RequireClanRole(["admin"]) + X-Current-Clan-Id
200: {"data": {"person_id": "...", "previous_person_id": "<uuid>|null",
               "message": <localized>}}
```

- Validates: the person exists in the active clan via `clan_memberships` (every
  API-created person has a membership row from `save_with_membership`) and is
  not soft-deleted → 404 `person_not_found` otherwise (same code the person
  routes use; no new error code needed for that case).
- Swap semantics: atomically (one UoW transaction) clears `is_founder` on the
  clan's current founder membership (if any) and sets it on the target's.
  Idempotent: designating the current founder returns 200 with
  `previous_person_id == person_id` and writes nothing new.
- Domain event `FounderDesignated(AuditableEvent)` (clan aggregate,
  `app/domain/clan/events.py` — same pattern as `ClanUpdated`) carrying
  `person_id` + `previous_person_id` → audit row in the same transaction via the
  fail-closed dispatcher.
- Aggregate ownership: **clan** (founder-ship is clan-level tree identity, not a
  person attribute) — command/handler in `app/application/clan/`, route in
  `app/api/v1/clans.py` beside the other `/clans/me/*` admin actions.

### 2. Exactly one live founder per clan — DB backstop (migration 023)

- Partial unique index: `CREATE UNIQUE INDEX uq_clan_memberships_one_founder ON
  clan_memberships (clan_id) WHERE is_founder = true`.
- Loud precheck (house style, 015/021/022 precedent): list clans with >1
  founder row and RAISE — operator resolves history manually, never silent
  repair. (Real deployments have none — the flag was unreachable; only
  out-of-band/test data could.)
- The swap runs clear-then-set inside one transaction, so the index never
  fires for the API path; it guards raw-SQL/out-of-band writers. Concurrent
  double-designation race → one writer hits the unique index → existing 23505
  → 409 `conflict` envelope (no new handler code).

### 3. Deterministic reads (belt-and-braces for legacy data)

`find_clan_founder` gains `ORDER BY cm.joined_at ASC NULLS LAST, cm.person_id`
— on any pre-index multi-founder data the tree roots at a stable founder
instead of a plan-dependent one. The export's own deterministic multi-founder
walk (`export_query_port.py`) is unchanged — the two authorities can no longer
disagree once the unique index holds (single founder), and on legacy data both
are now deterministic.

### 4. Semantics that do NOT change

- **An undesignated clan still 404s on `GET /tree`** (`clan_founder_not_found`)
  — now a legitimate onboarding state, not a dead end: the client's next step
  is the new endpoint. `docs/contracts/frontend-integration-guide.md` gets the
  flow note (create persons → admin designates thủy tổ → tree renders).
- Soft-deleting the current founder is allowed; the tree then 404s again until
  the admin re-designates (documented; no delete-blocking rule — keeps A3
  tight).
- `/tree/focus`/`ancestors`/`subtree`/`path` keep working without a founder
  (explicit-person endpoints); their `generation` fields simply populate once a
  founder exists.
- `clan_memberships.generation` (hand-entered) stays deprecated; the endpoint
  does not touch it.

### 5. The payoff — đời activates (and the B1 pins flip)

With a founder designated: `GET /tree` renders rooted at thủy tổ (đời 1);
`generation` populates on tree/focus/ancestors; GEDCOM export emits đời notes.
Test flips required by the B1 pin's own docstring:
- `test_tree_unreachable_for_api_managed_clan_KNOWN_DEFECT_H3` → becomes
  `test_tree_renders_after_founder_designation`: same setup + designation → 200,
  root id = designated person, root `generation == 1`, child đời 2. A
  *companion* test keeps the undesignated-clan 404 pinned as CORRECT behavior
  (new docstring: onboarding state, not defect).
- Journey 1 Stage 7's coupled asserts flip: add a designation stage (admin
  designates ông), then `generation_of_focus == 2` for con (ông đời 1 → con
  đời 2), ancestors carry generations.

## Error contract

No new error codes: 404 `person_not_found` (target invalid), 403 from existing
RBAC, 409 `conflict` (index race), plus one new success message key
`clan.founder_designated` (4 locales) for the response message.

## Docs (grep-verified per house lesson)

- `docs/contracts/rest-clans-api.md`: the new operation.
- `docs/contracts/frontend-integration-guide.md`: onboarding flow note
  (undesignated clan → tree 404 → designate).
- `docs/architecture/tree-read-model.md` + `domain-rules.md`: thủy tổ
  designation rule (exactly one live founder; swap endpoint; deterministic
  fallback on legacy data).
- **ADR-026**: exactly-one-founder decision (alternatives: founder-set,
  is_founder on person create — both rejected, reasons above).
- Grep sweep: `is_founder|thủy tổ|thuy to|clan_founder_not_found|founder` across
  docs/contracts + docs/architecture; disposition per hit.

## Tests (real-DB; RED-first via the B1 pin)

1. **RED**: flip the H3 pin FIRST — the flipped test (designate → tree works)
   fails against main (405/404 on the endpoint). That is A3's RED signal,
   exactly as the pin's docstring promised.
2. Endpoint integration tests (HTTP, real deps): designate → 200 + audit row;
   correction swap → previous_person_id populated + old founder cleared;
   idempotent re-designation; person of ANOTHER clan → 404 (two-sided: the
   foreign person id is real, just not in this clan); soft-deleted person →
   404; viewer/editor → 403; missing header → 400.
3. Đời correctness after designation: 3-generation family → `GET /tree` root
   generation 1, child 2, grandchild 3; `/tree/focus` generation_of_focus
   matches; export archive carries the generations.
4. Migration 023: unique-index sabotage test (raw SQL second founder → 23505)
   + precheck behavior consistent with house precedent (no dedicated precheck
   test — 015/021/022 precedent).
5. Race: two concurrent designations of different persons → exactly one wins
   (the loser gets 409 via the index; the app clear-then-set makes most
   interleavings serialize on the row anyway — the test proves no clan ends up
   with two founders).
6. B1 Journey-1 flip per §5.
