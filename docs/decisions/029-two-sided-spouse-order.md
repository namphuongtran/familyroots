# ADR-029: Two-Sided Per-Person `spouse_order` + Marriage Date-Order on Update

## Status
Accepted, shipped (2026-07-18).

## Context

The 2026-07-18 backend review (`docs/architecture/backend-review-2026-07-18.md`)
identified two related gaps in marriage-record integrity, grouped as A7 (**M1**
and **M7**; the review's A7 grouping also listed M4/M5 date-precision, which is a
separate theme shipped as a later PR — this ADR covers marriage-record integrity
only).

**M7 — `spouse_order` uniqueness was person1-oriented, but the model is
symmetric.** `marriages.person1_id`/`person2_id` carry no husband/wife marker —
either spouse can land in either column. `has_spouse_order_conflict`
(`backend/app/infrastructure/persistence/relationship_repository.py`) and the
partial unique index `uq_marriages_spouse_order (created_by_clan_id,
person1_id, spouse_order)` (migration `015_data_integrity`) both keyed on
`person1_id` only. Recording đa thê as `(H, W1, spouse_order=1)` then
`(W2, H, spouse_order=1)` — the same husband H, same rank, but with H in the
`person2` column the second time — checked W2's marriages (none) and passed:
H ended up with two "vợ cả" (order=1) undetected. `check_spouse_order`
(`backend/app/domain/relationship/validator.py`) had the same one-sided shape.

**M1 — marriage `PATCH` had no date-order re-validation.** The
`divorce_date ≥ marriage_date` cross-field rule lived only on
`MarriageCreateRequest` (a Pydantic model validator). `PATCH
/relationships/marriages/{id}` could set `divorce_date` earlier than the
stored `marriage_date` (or retro-date `marriage_date` past an existing
`divorce_date`) with no equivalent check in `MarriageCommandHandler.update`.

**True current behavior discovered in review (data was never corrupted):** a
pre-existing DB CHECK constraint, `marriages_divorce_after_marriage`
(migration `001_initial`), already refuses `divorce_date < marriage_date` on
every write, including `UPDATE` — so the bad state could never actually reach
storage. But `integrity_error_handler`
(`backend/app/core/exceptions.py`) only maps `CheckViolation`s whose message
matches the known `too_many_biological_parents` / `relationship_cycle` trigger
slugs (ADR-023); `marriages_divorce_after_marriage` is not one of them, so the
`CheckViolation` fell through to the generic handler and surfaced as a **raw
500**, not a clean 422 — the reachable failure mode was an ugly error shape,
not a data-integrity hole.

## Decision

**M7 — two-sided per-person `spouse_order` invariant, app-layer, no
migration.** Adding or updating a live (non-divorced) marriage that assigns
`spouse_order = N` must not leave **either** endpoint person with two live
non-divorced marriages carrying `spouse_order = N`. "Either endpoint's live
marriages" means rows where that person appears as `person1` **or**
`person2`.

- `has_spouse_order_conflict` widens its `WHERE` clause to check both columns
  for both candidate persons: `(person1_id IN (:a, :b) OR person2_id IN (:a,
  :b))`, keeping the existing `status <> 'divorced' AND is_deleted = false`
  and `exclude_marriage_id` clauses unchanged.
- `check_spouse_order` (the domain validator) takes both endpoint ids
  (`person_a`, `person_b`) instead of a single `person1_id`; `create` passes
  both marriage participants, `update` passes the marriage's fixed
  `person1_id`/`person2_id` pair.
- Runs on **create** and on **update** whenever `spouse_order` is set or the
  effective `status` is non-divorced (unchanged trigger conditions from the
  existing H2 re-validation-on-update rule — only the check's shape widened).
- **No migration.** The existing person1-keyed partial unique index
  (`uq_marriages_spouse_order`, migration 015) is retained as-is — it remains
  a valid (if narrower) race backstop for same-orientation concurrent
  inserts. This is an app-layer-only fix.

**M1 — `divorce_date ≥ marriage_date` enforced on the update path by a
pre-write domain check.** `MarriageCommandHandler.update` computes the
*effective* `marriage_date`/`divorce_date` (from `cmd.changes`, falling back
to the stored value for whichever date the PATCH didn't touch) and, if both
are present and `divorce_date < marriage_date`, raises `ValidationError
("relationship.divorce_before_marriage")` — a clean domain 422 — **before**
`marriage.update()`/`repo.save()` ever runs. This check runs strictly earlier
than the DB CHECK constraint on the same reachable path, so the constraint
functions purely as a backstop that in practice is never hit through the API;
the fix is that the *reachable* failure now returns a stable, documented 422
instead of an unmapped 500.

## Consequences

- **The flip is caught.** `(H, W1, 1)` then `(W2, H, 1)` now returns 409
  `relationship.duplicate_spouse_order` (previously 201); a PATCH that flips
  an existing marriage's `spouse_order` into collision via the person2 side is
  caught the same way. `backend/tests/integration/test_marriage_invariants.py`
  pins both the create-orientation-flip case and the update-flip case with
  real-DB fixtures, plus exclude-self (a marriage PATCHed to its own current
  order stays a no-op success).
- **Two accepted residuals, deliberate, not bugs:**
  1. **Polyandry over-reject.** Under the polygyny model this check enforces,
     a person cannot be the same-rank spouse (e.g. order=1, "vợ cả") in two
     *simultaneous live* marriages — so two different husbands each marrying
     the same wife at `spouse_order=1` collide on the wife's side of the
     check, even though neither husband individually holds a duplicate order.
     This over-rejects the rare polyandry / dual-live-household data case;
     acceptable under the polygyny convention this system targets. Workaround:
     distinct orders, or mark one marriage **divorced** (widowed does NOT free
     the slot — see residual 3). `test_polyandry_same_rank_rejected_ADR029`
     pins this as intended behavior, not a defect.
  3. **A widowed marriage still holds its `spouse_order`.** The check filters
     `status <> 'divorced'` only — married, widowed, and separated all count as
     live for ordering. So a husband widowed from his vợ cả (`order=1`,
     status `widowed`, the truthful record of the deceased first wife) cannot
     record a *new* wife at `order=1`: the widowed row still occupies rank 1,
     and the remarriage collides (409 `duplicate_spouse_order`). This is
     intended, not an over-reject: **vợ cả is historically singular** — a wife
     married after the first wife's death is vợ kế (a successor), not
     retroactively a second "first wife". Only marking the first marriage
     `divorced` (which would be untruthful for a death) or using a distinct
     order records the remarriage; the correct action is the distinct order.
     `test_widowed_marriage_still_blocks_same_spouse_order` pins this.
  2. **Concurrent-flip race is not DB-backstopped.** The existing unique index
     stays person1-keyed, so two *simultaneous* inserts in opposite
     orientations at the same order can still both pass the index (though the
     app-layer pre-check now catches the non-concurrent case, which was the
     actually-reported bug). This residual requires both writers to pick the
     same order and one to flip the pair — rare at human gia-phả editing
     rates. Future option if ever observed: a per-clan advisory-lock trigger
     (the ADR-025 pattern), not implemented here.
- **M1 data was never at risk** — the pre-existing
  `marriages_divorce_after_marriage` CHECK protected every write path,
  including the ones this ADR fixes. The change here is error-shape (a clean
  422 instead of a raw 500) and earlier detection (pre-write domain check
  instead of relying on the DB round-trip).
- **No new error code for M1** — the update path raises the same domain
  `ValidationError` shape the create path's Pydantic validator effectively
  enforces, tagged `relationship.divorce_before_marriage` (422); clients
  handle it identically to any other domain validation error.
- **Tracked FOLLOW-UP (broader than this ADR, found in review, not part of
  A7):** `integrity_error_handler` returns a raw 500 for **any** unmapped
  CHECK-constraint violation (SQLSTATE `23514`) whose message doesn't match
  one of the known trigger slugs — `marriages_divorce_after_marriage` was one
  instance of this general gap (now moot for the specific M1 path, since the
  domain pre-check intercepts it first, but the *general* handler gap is
  unchanged and other CHECK constraints — e.g. the precision CHECKs from
  ADR-025 — remain unmapped). A future pass should map known CHECK constraints
  to clean 4xx codes the same way the ADR-023 trigger slugs already are.

## Alternatives considered

- **Canonicalize marriage orientation (person1 = husband)** — rejected. This
  would need a gender-based anchor to decide which person becomes `person1`,
  but `persons.gender` includes `'unknown'`, so a canonicalization rule has no
  well-defined answer for every row; it would also require a backfill
  migration to re-orient every existing marriage row, plus updating every
  reader that currently treats `person1`/`person2` as unordered. The owner
  chose the no-migration two-sided check over an orientation rework with an
  undefined edge case and a required backfill.
