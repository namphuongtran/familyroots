# Kinship excludes divorced marriages (M8) — Design

**Date:** 2026-07-25
**Source finding:** M8 in `docs/architecture/backend-review-2026-07-18.md`.
**Owner decision:** exclude only `status = 'divorced'` (widowed/separated/married still
count) — matches the system-wide `has_active_marriage` convention.

## Problem

`find_relationship_path` (the kinship-path SQL, installed by migration 019's
frontier-BFS body) expands a `spouse` edge from **every** non-deleted marriage with
NO status filter:

```sql
SELECT CASE WHEN m.person1_id = f.id THEN m.person2_id ELSE m.person1_id END,
       'spouse'::VARCHAR
FROM public.marriages m
WHERE (m.person1_id = f.id OR m.person2_id = f.id)
  AND m.is_deleted = false
  AND m.created_by_clan_id = p_clan_id
```

`relationship_descriptor.describe_relationship` then resolves a kinship term purely
from the edge sequence (it never sees marriage status), so a **long-divorced**
marriage yields present-tense terms:
- `("spouse",)` → "Vợ/Chồng" for an ex-spouse;
- `("parent","spouse")` → "Mẹ kế/Bố dượng" (step-parent) for a parent's ex-spouse;
- `("child","spouse")` → "con dâu/con rể" for a child's ex-spouse;
- the in-law branches (`("parent","parent","child","spouse")`, etc.) → thím/mợ/dượng
  for relations that dissolved on divorce.

## Design (one SQL filter; no descriptor change, no i18n, matches existing convention)

Add `AND m.status <> 'divorced'` to the spouse-edge subquery — the column is
`Mapped[str]` (NOT NULL, defaults `'married'`), so `<> 'divorced'` needs no NULL
guard, and this is byte-for-byte the same predicate the marriage-uniqueness index
(migration 022:58,327), `spouse_order` index (015), and
`relationship_repository` (`:296`) already use. Divorced marriages stop being kinship
edges; **widowed / separated / married** spouses keep theirs.

### New migration `024_kinship_exclude_divorced`

`CREATE OR REPLACE FUNCTION public.find_relationship_path(...)` re-installing migration
019's **exact** frontier-BFS body (the live 3-arg + `p_max_depth` DEFAULT 20 function,
the only one migration 019 actually installs — its `_DOWNGRADE`/`_BFS_011` string is
used only by 019's own `downgrade`) with the one added line on the spouse edge.
- `upgrade()` installs the filtered body.
- `downgrade()` re-installs migration 019's unfiltered body verbatim (so the chain is
  reversible to exactly the prior function).
- No schema change — pure function replacement, matching how 019 itself was authored.

### Why the descriptor is untouched

The descriptor operates only on edge types + person attributes. Once the SQL stops
emitting `spouse` edges for divorced marriages, the descriptor never sees them, so
every affected term (direct spouse, step-parent, child-in-law, affinal in-laws)
disappears together — no per-term branching, no new i18n keys. Clean separation.

## Consequences (documented, intentional)

- A pair connected **only** through a dissolved marriage now returns **no path** →
  the kinship endpoint reports no current relationship (correct: divorce ends
  affinity). If they share children, they remain connected via `parent`/`child`
  edges (co-parent), described by those edges — not as spouses.
- Ex-step / ex-in-law relations reachable only across a divorced spouse edge drop
  from kinship results. Blood kin are never affected (parent/child edges unchanged).
- **Widowed** spouses still resolve to "Vợ/Chồng"; a widowed step-parent still
  "Mẹ kế/Bố dượng" — bereavement does not end the kinship, only divorce does
  (consistent with `has_active_marriage`).
- Not a data change — the marriage row and its `status` are untouched; the tree
  read-model still lists the marriage with its real status for the client to render.

## Blast radius

`find_relationship_path` is consumed only by `tree_repository.py:133`;
`describe_relationship` only by `tree/handlers.py:171` — one feature (the
relationship-path / kinship-descriptor endpoint). Nothing else traverses the function.

## Tests (real-DB; RED-first)

1. **Divorced direct spouse → no spouse kinship.** A & B married then `status='divorced'`,
   no other connection → `find_relationship_path(A,B)` returns EMPTY and the endpoint
   reports no relationship. RED today (returns a `spouse` path → "Vợ/Chồng").
2. **Divorced step-parent gone.** Child C, parent P, P married X then divorced →
   path C→X no longer `("parent","spouse")` → not "Mẹ kế/Bố dượng". RED today.
3. **Widowed spouse still counts (control, must stay GREEN).** A & B married,
   `status='widowed'` → still a `spouse` path → still "Vợ/Chồng". Pins that the filter
   is divorced-only, not all-non-married.
4. **Separated spouse still counts (control).** `status='separated'` → still a spouse
   path (matches `has_active_marriage`).
5. **Blood kin via shared children unaffected.** A & B divorced but share child C →
   A↔B still connected via C (`child`/`parent` edges), described by those edges, never
   as spouses. Proves divorce removes only the spouse edge, not the people.
6. Existing kinship / relationship-path / tree suites stay green (they seed
   `married`/default-status marriages, which still traverse).

## Docs

- `docs/architecture/domain-rules.md`: the kinship descriptor now traverses only
  non-divorced marriages (`status <> 'divorced'`), alongside the existing
  "both birth dates exact" clause — divorced marriages are excluded from kinship
  paths (widowed/separated persist), matching `has_active_marriage`.
- `docs/ops/migrations.md`: note migration 024 (function replacement, reversible).
- Grep sweep: `find_relationship_path|kinship|divorced|spouse|descriptor` across
  docs/contracts + docs/architecture; per-hit dispositions.

No new ADR — this enforces the existing `status <> 'divorced'` convention (ADR-025
already owns the "active = non-divorced" semantics) in the one place that diverged.
