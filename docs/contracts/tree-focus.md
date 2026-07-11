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
- `focus_subtree` (node|null) — nested node; each node adds `generation` (computed), `branch_id`/`branch_name`/`branch_order` (chi), `has_more_descendants` (bool, drill affordance) to the standard person/spouse fields (`spouses[].spouse_order`, `membership_role` = blood/spouse/adopted). Children ordered by `birth_order` → `birth_date` → name.

**Errors:** focus person not in the clan (or soft-deleted / unknown) → 404 `person_not_found` (envelope). Never reveals cross-clan existence.

**Notes:** đời is derived on read from the graph; `clan_memberships.generation` is not the source here. `branch_*`/`has_more_descendants` are focus-only — the older `/tree` and `/tree/subtree` responses are unchanged.
