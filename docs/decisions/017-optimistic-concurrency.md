# ADR-017: Required Optimistic Concurrency Control on Genealogy Writes

## Status
Accepted (2026-07-12 — shipped)

## Context
The 2026-07-12 data-integrity review (H1) found no version tracking anywhere in the
write path: `person_mapper.apply_to_orm` (and the equivalent marriage/parent-child
mappers) write **all** updatable columns from the in-memory entity back to the row on
every save. Two concurrent editors doing read-modify-write silently clobber each
other — the second commit reverts every field the first editor just changed, with no
error to either client. For irreplaceable gia phả data (dates, names, relationships)
a silent lost update is worse than a visible failure.

No frontend exists yet for any client (web/mobile are still building against these
contracts). That made the version field an **optional add-on now, load-bearing
later** trap: if OCC ships as optional, no client will send `expected_version` until
someone hits a real data-loss incident and traces it back to this gap — the same
failure mode that let H1 go unnoticed. Making it required from day one closes the
hole before any client code exists to skip it.

## Decision
- Add `version INTEGER NOT NULL DEFAULT 1` to the three genealogy write tables:
  `persons`, `marriages`, `parent_child` (migration `015_data_integrity`,
  `server_default '1'` so existing rows backfill implicitly). Events, documents,
  branches, and clans are **not** in scope for v1 — those aggregates don't yet show
  the same field-level lost-update risk (documents/events are narrower writes;
  clans go through a small explicit whitelist), and adding OCC everywhere at once
  would be unverified scope creep. They're deferred, not rejected.
- `PersonResponse`, `MarriageResponse`, `ParentChildResponse` gain `version: int`
  (≥1). `PersonUpdateRequest`, `MarriageUpdateRequest`, `ParentChildUpdateRequest`
  gain a **required** `expected_version: int = Field(..., ge=1)` — not optional.
  Missing it is a standard 422 Pydantic validation error; there is no silent
  fallback to "just update the latest version".
- Enforcement is an atomic conditional `UPDATE`, not the SQLAlchemy ORM
  `version_id_col` mechanism:
  ```sql
  UPDATE persons SET ..., version = version + 1
  WHERE id = :id AND version = :expected
  ```
  `rowcount == 0` after this statement means either the row doesn't exist or the
  version didn't match; the repository re-reads the current version and raises
  `ConflictError("stale_write", detail={"current_version": <int>})` → HTTP 409.
  `version_id_col` was rejected: it raises `StaleDataError` on session flush, which
  (a) is harder to map cleanly onto the 409 `stale_write` contract without catching
  a SQLAlchemy-specific exception deep in the repository, and (b) couples the
  domain-facing save() call to an ORM identity-map mechanic instead of a plain SQL
  predicate that stays visible and testable at the query level. The explicit
  conditional `UPDATE` keeps the rule visible in the same statement that does the
  write, and needs no `SELECT ... FOR UPDATE` — the `WHERE version =` predicate
  makes the row-level check atomic with the write itself.
  Full-column `apply_to_orm`/`values(**UPDATABLE_FIELDS)` copying stays exactly as
  it was — it's safe now because the version check already proves the read that
  produced these values was fresh; the version predicate is the fix, not a rewrite
  of the mapping strategy.
- Successful update increments `version` by exactly 1 and the response echoes the
  new value, so the client's next PATCH already carries the right
  `expected_version` without an extra round-trip.
- `DELETE`/`restore` (and `claim`, which doesn't touch these tables) do **not**
  require `expected_version` — those paths are role-gated, soft, and restorable, so
  a lost *delete* isn't the same failure mode as a lost *field edit*. They still
  call the same repository `save()` and still **bump `version`** on every write
  (delete and restore included) so that a concurrent in-flight PATCH against the
  same row correctly observes a stale version and gets 409, instead of quietly
  overwriting a state the delete/restore already changed underneath it.
- Domain entities carry `version` as a plain field, explicitly excluded from each
  aggregate's `_UPDATABLE_FIELDS`/whitelist — it is server-managed state, never a
  client-writable field.

## Consequences
Easier: field-level lost updates on the three riskiest tables are now impossible at
the database level — the conditional `UPDATE`'s `rowcount` is the single source of
truth for "did I just overwrite someone else's edit," with no window for a race
between check and write.

Harder: every PATCH client (there is none yet, but web/mobile will be the first)
must perform a prior `GET` (or use the version echoed by `create`/a previous
response) to obtain `expected_version` before it can update a person, marriage, or
parent-child edge — there is no "just PATCH it" shortcut. Clients must implement a
reload-on-409 flow: on `stale_write`, refetch the record (picking up the fresh
`version` from `detail.current_version` or a follow-up `GET`), and re-apply the
user's edit on top of the latest state rather than resubmitting blindly. Because the
scope is deliberately 3 tables, the same lost-update risk still exists un-mitigated
on events/documents/branches/clans until a follow-up closes that gap.
