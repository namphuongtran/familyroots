# Marriage-Record Invariants (A7 — M1 + M7) — Design

**Date:** 2026-07-18
**Source findings:** M1 + M7 in `docs/architecture/backend-review-2026-07-18.md`.
**Owner decision (M7):** two-sided per-person spouse_order check (over
canonicalize-orientation) — no gender dependency, no data migration.
**Scope note:** the review's original "A7" grouping also listed M4 + M5
(date-precision); those are a SEPARATE cohesive theme and ship as the next PR.
This PR is marriage-record integrity only.

## The two holes

- **M1 — Marriage PATCH bypasses `divorce_date ≥ marriage_date`.** The cross-field
  validator lives only on `MarriageCreateRequest` (`app/schemas/marriage.py:32-38`).
  `PATCH /relationships/marriages/{id}` can set `divorce_date` earlier than the
  existing `marriage_date` (or retro-date `marriage_date` after an existing
  `divorce_date`) → 200, recording a divorce before the wedding. The update
  handler already re-checks status/spouse_order (H2) but NOT this.
- **M7 — `spouse_order` uniqueness is person1-oriented only.** `has_spouse_order_conflict`
  (`relationship_repository.py:283-306`) and the partial unique index
  (`uq_marriages_spouse_order (clan, person1_id, spouse_order)`, migration 015)
  key on `person1_id`. `person1`/`person2` are symmetric in the model (no husband
  marker), so recording đa thê as `(W2, H, order=1)` instead of `(H, W1, order=1)`
  checks W2's marriages (none) and passes — H ends up with two "vợ cả".

## Design

### M1 — re-validate date order on the update path

The cross-field rule must run against the **effective** dates after the PATCH is
merged (either date may be absent from `changes`). In `MarriageCommandHandler.update`
(beside the existing H2 re-checks), compute effective `marriage_date`/`divorce_date`
from `cmd.changes` falling back to the current `marriage.*`, and if both present and
`divorce_date < marriage_date` raise the SAME error the create validator raises
(`ValidationError`/`ValueError` → 422; match the exact type the create path yields
so the code/envelope is identical). No new error code. (Schema-level can't do it —
PATCH fields are optional and the schema can't see stored values.)

### M7 — two-sided per-person spouse_order invariant

**Invariant (ADR-029):** adding/updating a live non-divorced marriage that assigns
`spouse_order = N` must not leave **either endpoint** with two live non-divorced
marriages carrying `spouse_order = N`. "Either endpoint's live marriages" = rows
where that person is `person1` **or** `person2`.

- Catches the flip: writing `(W2, H, 1)` while `(H, W1, 1)` is live → H would have
  two order-1 marriages → reject `relationship.spouse_order_conflict` (existing
  code). Also catches the plain same-orientation dup (unchanged behavior).
- `has_spouse_order_conflict` SQL widens from `WHERE person1_id = :p1` to
  `WHERE (:p1 IN (person1_id, person2_id) OR :p2 IN (person1_id, person2_id))`
  with the same `status <> 'divorced' AND is_deleted = false` and `exclude_id`
  clauses. The validator wrapper takes both endpoint ids (create passes both;
  update passes the marriage's fixed pair).
- Runs on create AND update (the update path already calls `check_spouse_order`
  when spouse_order/status changes — it switches to the two-sided form with both
  ids).

**Accepted consequences (documented in ADR-029, intentional under the polygyny
model):**
1. A person cannot be recorded as the same-rank spouse (e.g. vợ cả) in **two
   simultaneous live** marriages. In polygyny (one husband, ordered wives) this
   only bites the rare polyandry / dual-live-household data case — acceptable;
   the workaround is distinct orders or divorced/widowed status on one.
2. **No new DB backstop.** The existing person1-keyed partial unique index stays
   (race-safe for same-orientation concurrent inserts). The two-sided invariant
   is not expressible as a plain unique index and the owner chose no migration,
   so the app-layer check is the fix. Residual: a *concurrent flip race* (two
   simultaneous inserts in opposite orientations, same order) is not
   DB-backstopped — rare (both writers must pick the same order and one must flip
   the pair), and the non-concurrent flip (the actual reported bug) IS closed.
   Named in ADR-029; a per-clan-advisory-lock trigger (ADR-025 pattern) is the
   future option if this race is ever observed.

## What does NOT change

- Marriage API contract, response shape, error codes (M1 reuses the create
  validator's error; M7 reuses `relationship.spouse_order_conflict`).
- `person1`/`person2` symmetry (no canonicalization, no migration).
- The tree's đa thê `mother_id`/`spouse_order` rendering (reads unchanged).
- ADR-025's marriage unique-pair index (per-pair, separate concern).

## Tests (real-DB; RED-first)

1. **M1 create still blocks** (regression pin) + **M1 update now blocks**:
   PATCH divorce_date earlier than the stored marriage_date → 422 (RED today: 200);
   PATCH marriage_date later than the stored divorce_date → 422; a valid PATCH
   (divorce after marriage) → 200. Assert the exact error code matches the create
   path's.
2. **M7 flip is caught**: create `(H, W1, order=1)`; create `(W2, H, order=1)`
   → `relationship.spouse_order_conflict` (RED today: 201). Positive controls:
   `(H, W2, order=2)` → 201 (distinct order ok); the đa thê happy path
   `(H,W1,1)+(H,W2,2)` both succeed and the tree shows two correctly-ordered wives.
3. **M7 update flip**: PATCH an existing marriage's spouse_order to collide with a
   co-wife via the person2 side → conflict; exclude-self works (PATCH a marriage to
   its own current order → ok).
4. **Accepted-consequence pin**: the polyandry over-reject is asserted as the
   DEFINED behavior (a person as order-1 in two live marriages → conflict), with a
   docstring citing ADR-029 so it reads as intentional, not a bug.
5. **Divorced excluded**: `(H,W1,1 married)` + `(H,W2,1 divorced)` → allowed
   (divorced leaves the live set); pins the status filter.
6. Existing marriage + relationship + tree suites stay green.

## Docs

- **ADR-029**: the two-sided spouse_order invariant, the rejected
  canonicalize-orientation alternative, and the two accepted residuals.
- `docs/decisions/README.md` row.
- `docs/contracts/rest-relationships-api.md`: spouse_order uniqueness is
  per-person/orientation-independent; divorce_date ≥ marriage_date enforced on
  create AND update.
- Grep sweep: `spouse_order|divorce_date|vợ cả|marriage` across docs/contracts +
  docs/architecture; per-hit dispositions.
