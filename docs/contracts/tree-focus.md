# Contract: GET /api/v1/tree/focus/{person_id}

Consolidated read model for the interactive focus-tree UI (web/mobile). One round-trip per refocus.

**Auth:** Bearer JWT + `X-Current-Clan-Id`; role ≥ viewer.

**Query params:**
- `descendants` (int, default 2, 1–6) — generations below the focus person.
- `ancestors` (int, default 50, 0–50) — ancestor generations for the breadcrumb.

**Response** `{"data": FocusView}`:
- `focus_person_id` (str)
- `generation_of_focus` (int|null) — đời computed from the graph; thủy tổ = 1; null if the focus is not descended from a founder.
- `ancestors` (list) — strict ancestors, thủy-tổ-first, excluding focus; each `{id, full_name, gender, birth_date, death_date, avatar_url, generation, is_founder}`.
- `focus_subtree` (node|null) — nested node; each node adds `generation` (computed), `branch_id`/`branch_name`/`branch_order` (chi), `has_more_descendants` (bool, drill affordance), `mother_id` (str uuid|null — the child's female parent, i.e. which wife) and `mother_spouse_order` (int|null — that mother's `spouse_order` in her marriage to the father; đa thê "con bà cả/hai/ba") to the standard person/spouse fields (`spouses[].spouse_order`, `membership_role` = blood/spouse/adopted). Children ordered by `birth_order` → `birth_date` → name.

**Errors:** focus person not in the clan (or soft-deleted / unknown) → 404 `person_not_found` (envelope). Never reveals cross-clan existence.

**Notes:** đời is derived on read from the graph; `clan_memberships.generation` is not the source here. đời is **intrinsic** — computed from a full-depth ancestor lookup (fixed max 50), independent of the caller's requested `ancestors` breadcrumb window. `generation_of_focus` and every node's `generation` are always computed the same way, regardless of how small `ancestors` is; a small `ancestors` value only shrinks the breadcrumb list, it never nulls out generations. `generation` is `null` only when the person isn't descended from a founder (or the clan has no founder). `branch_*`/`has_more_descendants` are focus-only — the older `/tree` and `/tree/subtree` responses are unchanged. `mother_id` is `null` when no mother edge is recorded for that child (see `rest-tree-api.md` for the "one female-parent edge per child" assumption).
