# Data Integrity Design Spec

**Date:** 2026-07-12
**Branch:** `feat/data-integrity` (off `main` @ b48a74d)
**Purpose:** Close the five code-verified data-integrity findings from the 2026-07-12
deep review that let irreplaceable genealogy data be silently lost or corrupted:
C1 last-admin race, H1 lost updates, H2 update-validator bypass, M3 spouse_order
collisions, M1 cycle-detection depth cap.

**Owner decisions (2026-07-12):**
- OCC: `version` column **required** on PATCH, scoped to the 3 genealogy tables
  (`persons`, `marriages`, `parent_child`). Events/documents/branches/clans: not in v1.
- H2: **re-validate on update** (not immutability) — genealogy needs corrections.

---

## Item 1 — Optimistic concurrency (H1: silent lost updates)

### Problem (verified)
No version tracking anywhere; `person_mapper.apply_to_orm` writes **all** ~35
`UPDATABLE_FIELDS` columns from the in-memory entity
(`app/infrastructure/persistence/person_mapper.py:141-148`). Two concurrent editors
do read-modify-write; the second commit silently reverts the first editor's fields.
Same pattern for marriages/parent-child (`relationship_repository.py`).

### Contract (frozen — frontend binds this)
- `persons`, `marriages`, `parent_child` responses gain `"version": <int>` (≥1).
- PATCH request DTOs gain **required** `expected_version: int`.
  - Missing → 422 (standard Pydantic validation error).
  - Mismatch → **409** with code **`stale_write`**, `detail: {"current_version": <int>}`.
    Client UX: reload the record, show "người khác vừa sửa", re-apply the edit.
- Successful update increments `version` by exactly 1 and returns the new value.
- DELETE/restore/claim and all reads do NOT require a version (only PATCH races
  destroy field-level data; delete is role-gated + soft + restorable).

### Storage & enforcement
- Migration `015_data_integrity`: `version INTEGER NOT NULL DEFAULT 1` on the 3 tables
  (server_default `'1'` so existing rows backfill implicitly).
- Enforcement is **atomic at the DB**: conditional
  `UPDATE ... SET ..., version = version + 1 WHERE id = :id AND version = :expected`
  → `rowcount == 0` ⇒ raise `ConflictError("stale_write", detail={"current_version": <reload>})`.
  No SELECT FOR UPDATE needed on this path.
- Implementation seam: repository `save()` for updates takes the expected version
  (threaded from the command); `apply_to_orm` full-column copy stays (safe — the
  version check proves the read was fresh). Domain entities carry `version` as a
  plain field (not in `_UPDATABLE_FIELDS`).
- ORM alternative (`version_id_col`) rejected: it raises `StaleDataError` on flush,
  which is harder to map cleanly to the 409 contract and couples the domain to
  SQLAlchemy semantics. Explicit conditional UPDATE keeps the rule visible.

### Docs in the same PR
`docs/contracts/{rest-persons-api,rest-relationships-api}.md` (version field +
required expected_version + 409), `docs/contracts/error-codes.md` (`stale_write`),
i18n `error.stale_write` ×4 locales, ADR-017 (optimistic concurrency), data-model.md.

---

## Item 2 — Last-admin race (C1)

### Problem (verified)
`change_role` guards only **self**-demotion and counts admins without any lock
(`app/application/clan/handlers.py:101-135`); `remove_user` has **no** last-admin
guard at all (`:137-159`). Two concurrent demotions/removals leave a clan with 0
admins — permanently unmanageable (approve/roles/claims all admin-gated).

### Behavior
Invariant: **a clan always has ≥ 1 admin** (with `is_approved = true`).
- `change_role` away from `admin` (any target) and `remove_user` of an admin (any
  target) must both enforce it.
- Codes: demote → existing `clan.last_admin_cannot_demote` (403); remove →
  new `clan.last_admin_cannot_remove` (403, + i18n ×4, + error-codes.md).

### Enforcement
In both handlers, when the operation would reduce the admin set:
`SELECT id FROM user_clan_roles WHERE clan_id = :clan AND role = 'admin' AND is_approved = true FOR UPDATE`
(new repo method `lock_admin_rows(clan_id)`), then count the locked rows and apply
the invariant **inside the same transaction** as the mutation. Concurrent reducers
serialize on the row locks; the second sees the post-commit state and gets 403.
The guard now also runs when `target != actor` (the old self-only condition is the bug).

---

## Item 3 — Re-validate relationships on update (H2)

### Problem (verified)
`ParentChildCommandHandler.update` applies `changes` with **zero** validation
(`app/application/relationship/handlers.py:117-125`); `relationship_type` is in
`_PARENT_CHILD_UPDATABLE_FIELDS`. PATCHing `adopted → biological` bypasses the
max-2-biological-parents and ≥12-year rules that `create` enforces.

### Behavior
- `ParentChildCommandHandler.update`: if `changes` touches `relationship_type`,
  re-run `validate_parent_child(parent_id, child_id, new_type, clan_id)` with the
  bio-parent count **excluding the edge being updated** (new validator param
  `exclude_link_id`). Cycle check is skipped — parent/child ids are immutable on
  update (assert that in the entity whitelist; they are not updatable today).
- `MarriageCommandHandler.update`: if `changes` touches `status` and the new status
  is `married`, re-run the duplicate-active-marriage check excluding this marriage
  (same `exclude_link_id` pattern) — prevents divorce→married flip creating a
  second active duplicate that the create path would have blocked.
- Violations raise the same domain codes as create (409/422 per existing mapping).

---

## Item 4 — spouse_order uniqueness (M3)

### Problem (verified)
`spouse_order` has only a `> 0` CHECK; nothing prevents two of a father's marriages
both having `spouse_order = 1` → vợ cả/vợ hai ordering nondeterministic
(`ORDER BY m.spouse_order ASC NULLS LAST` in the tree SQL).

### Enforcement
- Migration `015_data_integrity` adds partial unique index:
  `uq_marriages_spouse_order (created_by_clan_id, person1_id, spouse_order)
  WHERE spouse_order IS NOT NULL AND is_deleted = false AND status = 'married'`.
  (`person1` is the clan-line spouse by convention; `spouse_order` is defined from
  person1's perspective — matches model comment.)
- Migration pre-check: SELECT for existing violations; if found, **fail the migration
  with a clear message** listing the offending rows (operator resolves data first —
  we do not silently renumber history). Fresh DBs are unaffected.
- Validator: on create/update where `spouse_order` is set (or status flips to
  `married`), check for an existing active marriage of `person1` with the same order
  (excluding self) → 409 **`relationship.duplicate_spouse_order`** (+ i18n ×4 +
  error-codes.md). The index remains the backstop for races (23505 → 409).

---

## Item 5 — Unbounded cycle detection (M1)

### Problem (verified)
`is_ancestor` calls `get_ancestors_flat(:id, :clan_id, 20)`
(`relationship_repository.py:249-257`) — a display function with a hard depth cap.
Clans deeper than 20 đời can create real cycles that pass validation.

### Enforcement
Replace with a dedicated recursive CTE (inline SQL in the repository, not a new DB
function): walk `parent_child` upward from the proposed parent, clan-scoped
(`created_by_clan_id = :clan_id AND is_deleted = false`), **no depth limit**, with
the standard path-array cycle guard (`NOT person_id = ANY(path)`) so traversal
terminates even on already-corrupt data. Return EXISTS(child in ancestor set).
Same signature, same call sites — behavior change only in depth.

---

## Testing (real-DB, two-sided, sabotage-verified — ADR-016 discipline)

- **OCC:** stale PATCH → 409 `stale_write` + `current_version`; fresh PATCH →
  version+1 echoed; missing `expected_version` → 422; two true-concurrent sessions
  (second gets 409, first's fields intact — the H1 scenario reproduced then fixed);
  all three tables covered.
- **C1:** two concurrent sessions demoting/removing the last two admins → exactly one
  succeeds; single-admin self-demote → 403; single-admin removal by (hypothetical)
  other-admin path → 403; sabotage: removing the FOR UPDATE makes the race test fail.
- **H2:** adopted→biological with 2 existing bio parents → 409; with age gap < 12 →
  422; legitimate correction (no rule broken) still succeeds; marriage
  divorced→married when a duplicate active marriage exists → 409.
- **M3:** second `spouse_order = 1` for same person1 → 409 (validator) and the index
  blocks a raw-SQL bypass (23505→409); soft-deleted/divorced rows do NOT collide.
- **M1:** build a 25-generation chain; adding an edge that closes the loop at the top
  → rejected; regression: 20-generation chain still validates normally.
- Full gate: `uv run pytest -q && uvx ruff check . && uvx ruff format --check . &&
  uv run mypy app/ tests/ && uv run lint-imports`.

## Explicitly NOT in this PR
OCC for events/documents/branches/clans; `If-Match`/ETag transport (body field
chosen); M4 create-TOCTOU advisory lock (follow-up; much rarer than C1/H1); lunar
giỗ scheduler (next PR); any backup/export work (separate ops track).
