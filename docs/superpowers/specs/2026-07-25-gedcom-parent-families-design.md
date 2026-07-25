# GEDCOM parent grouping by relationship type (M6) — Design

**Date:** 2026-07-25
**Source finding:** M6 in `docs/architecture/backend-review-2026-07-18.md`.
**Owner decision:** group a child's parents by `relationship_type`; within a type use a
real marriage FAM, else synthesize ONE couple FAM for exactly-two parents, else
single-parent FAMs. NEVER pair across types.

## Problem

`_link_children` (`gedcom_export.py:172-201`) collects a child's parents, sorts them by
**UUID string order**, and pairs them **two-at-a-time** (`parent_items[0]` +
`parent_items[1]`) into a FAM — ignoring `relationship_type`, gender, and whether the
two are actually married. For a child with a biological mother + biological father +
adoptive father (3 parents), UUID order can pair e.g. `(adoptive_father,
biological_father)` as HUSB/WIFE of a **couple FAM that never existed**, leaving the
biological mother as a lone single-parent FAM. The exported gia phả then asserts a
fictional marriage between two men / a bio-father and an adoptive-father.

`relationship_type` ∈ `{biological, adopted, step, foster}` (migration 001:405).
PEDI today: `rel != "biological"` → `2 PEDI <rel>` on the child's FAMC line
(`:199,218,281`).

## Design (rewrite `_link_children`'s pairing; multi-FAMC by type; no migration, no new ADR)

Per child (deterministic: children sorted by `str(id)`):

1. **Dedup** the child's parents (keep the first `relationship_type` seen per parent).
2. **Partition by `relationship_type`** into groups: biological, adopted, step, foster.
3. **Process types in a deterministic order** (sorted type name), and within a type
   process parents sorted by `str(id)`. For each type's parent list `pts`
   (`pedi = None if type == "biological" else type`):
   a. **Real marriages first.** Greedily consume any two parents of `pts` who are an
      actual married couple (`frozenset({a,b})` in `family_by_pair`): attach the child
      to that existing marriage FAM. Both are marked consumed.
   b. **Remaining parents of this type:**
      - **exactly two** unconsumed → synthesize ONE couple FAM (HUSB/WIFE via the
        existing `_husb_wife` gender rule; keyed `frozenset({a,b})` in `family_by_pair`
        so co-children of the same synthetic couple share it).
      - **one** unconsumed (or each of 3+ that couldn't pair) → single-parent FAM
        (keyed `frozenset({parent})`), as today.
   c. Each attachment appends `child_id` to the FAM's `children` and
      `(fam, pedi)` to `child_famc[child_id]`.
4. **Never** form a FAM whose two spouses come from **different** relationship types.

A child thus receives one `FAMC` per family unit — e.g. a birth-family FAM (no PEDI)
plus an adoptive-family FAM (`PEDI adopted`) — which is the correct GEDCOM 5.5.1
multi-FAMC modeling.

### Determinism & dedup preserved

- FAM sort keys unchanged: marriage `(0, marriage_id)`, synthetic couple
  `(1, husb, wife)`, single-parent `(2, parent)`.
- `family_by_pair` still deduplicates synthetic couple / single-parent FAMs across
  children (keyed by the parent frozenset), so two children of the same unmarried
  couple share one FAM. A shared FAM can carry different PEDI per child because PEDI is
  stored per `child_famc` entry, not on the FAM.
- Output is fully deterministic (sorted types, sorted parents, greedy marriage pairing
  in sorted order).

### Same-type same-gender couples

Two parents of ONE type (e.g. a same-sex adoptive couple) still pair into a couple FAM —
`_husb_wife` falls back to `person1 → HUSB` for same/unknown gender, exactly as the
marriage-FAM path already does. Type grouping only prevents CROSS-type pairing.

## What does NOT change

- Marriage FAMs, single-parent FAM shape, PEDI value mapping (`2 PEDI <rel>`), FAMS
  back-references, HUSB/WIFE gender rule, submitter/header/TRLR.
- The JSON export (unaffected — this is GEDCOM-only).
- **Out of scope (noted, not fixed here):** `2 PEDI step` is not a standard GEDCOM
  5.5.1 PEDI value (`{adopted, birth, foster, sealing}`) — a pre-existing value-mapping
  question, tracked separately; M6 is about not inventing couples.

## Tests (unit + real-DB; RED-first)

Unit (`test_gedcom_export.py` patterns — call the export on in-memory persons/edges/
marriages, assert the emitted FAM/FAMC/HUSB/WIFE lines):

1. **The bug:** child with biological mother + biological father + adoptive father
   (3 parents, no marriages) → NO FAM pairs the adoptive father with a biological
   parent; the two biological parents form ONE couple FAM (child FAMC, no PEDI), the
   adoptive father is a single-parent FAM (child FAMC `PEDI adopted`). **RED today**
   (UUID order can pair bio+adoptive as a couple).
2. **Biological couple still grouped:** two biological parents (unmarried) → one couple
   FAM, HUSB/WIFE by gender, child FAMC no PEDI. (Regression pin.)
3. **Real marriage used within type:** the two biological parents ARE married → child
   attaches to the marriage FAM (no synthetic couple), `1 DIV` etc. preserved.
4. **Adoptive couple:** two adoptive parents → ONE adoptive couple FAM, child FAMC
   `PEDI adopted`; not mixed with any biological parent.
5. **Single adoptive parent alongside a bio couple:** bio mother+father (couple) +
   one adoptive mother → child has exactly two FAMC: the bio couple (no PEDI) and the
   adoptive single-parent (`PEDI adopted`). No cross-type couple.
6. **Determinism:** exporting the same graph twice is byte-identical; parents given in
   any input edge order produce the same FAMs.
7. Real-DB end-to-end (`test_clan_export_gedcom.py`): seed a child with mixed-type
   parents, hit the export endpoint, parse the GEDCOM, assert no invented couple and
   the expected multi-FAMC.

Existing GEDCOM/JSON export suites stay green.

## Docs

- `docs/contracts/rest-exports-api.md:170`: rewrite the parent-child grouping row —
  parents are grouped by relationship type; within a type a real marriage FAM is used,
  else exactly-two parents form one couple FAM, else single-parent FAMs; parents of
  different types are never paired; a child gets one FAMC per family unit (birth /
  adoptive / …), each with its PEDI.
- `docs/decisions/020-clan-export-formats.md` if it details GEDCOM FAM construction.
- Grep sweep: `FAMC|PEDI|couple|parent|relationship_type|HUSB|WIFE` across
  docs/contracts + docs/decisions; per-hit dispositions.

No new ADR — refines the existing GEDCOM export contract (ADR-020) to stop asserting
marriages that never existed.
