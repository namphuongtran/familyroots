"""Tree SQL functions emit date precision/display instead of the approx flags.

`get_family_tree_flat` and `get_ancestors_flat` (migration 005) expose
`birth_date`/`death_date` (+ `get_family_tree_flat` also exposes
`birth_date_approx`/`death_date_approx`) via a named `RETURNS TABLE`. Task 4 of the
HistoricalDate contract needs the builder to assemble a `HistoricalDate`
(`{date, precision, display, lunar}`) for every tree node, which requires the
`*_precision`/`*_display` columns (added to `persons` by migration 012) to flow
through these functions too.

Postgres does not allow `CREATE OR REPLACE FUNCTION` to change a function's
`RETURNS TABLE` column list — that requires `DROP FUNCTION` + `CREATE FUNCTION`.
This migration does exactly that for both functions:

  - ADDS `birth_date_precision`, `birth_date_display`, `death_date_precision`,
    `death_date_display` to each function's `RETURNS TABLE` + `SELECT`.
  - REMOVES `birth_date_approx`/`death_date_approx` from `get_family_tree_flat`
    (it never selected them on `get_ancestors_flat`) so Task 5's later `approx`
    column drop is safe against these functions.
  - Leaves every other column, the clan-scoping (`created_by_clan_id`) predicates,
    and the cycle guards (`NOT (p.id = ANY(path))`) untouched — this is a pure
    column swap on top of migration 005's scoped definitions.

`find_relationship_path` (also touched by migration 005) is NOT part of this
migration — it still selects `birth_date_approx` via a separate `persons` JOIN in
`tree_repository.find_path`, not from its own `RETURNS TABLE`, and switching that
to precision is Task 5's job (kinship `_age_rank`), not this one.

`downgrade()` restores migration 005's scoped definitions verbatim (with
`birth_date_approx`/`death_date_approx`, without precision/display).

Revision ID: 013_tree_date_precision
Revises: 012_historical_date_precision
"""

from __future__ import annotations

from alembic import op

revision: str = "013_tree_date_precision"
down_revision: str | None = "012_historical_date_precision"
branch_labels = None
depends_on = None


# --- New definitions: precision/display in, approx out -----------------------------
_GET_FAMILY_TREE_FLAT_NEW = """
CREATE FUNCTION public.get_family_tree_flat(
    p_root_id         UUID,
    p_clan_id         UUID,
    p_max_generations INT DEFAULT 10
)
RETURNS TABLE (
    person_id UUID, full_name VARCHAR, birth_name VARCHAR, posthumous_name VARCHAR,
    gender VARCHAR, birth_date DATE, birth_date_precision VARCHAR, birth_date_display VARCHAR,
    death_date DATE, death_date_precision VARCHAR, death_date_display VARCHAR,
    birth_place VARCHAR, generation SMALLINT,
    avatar_url VARCHAR, membership_role VARCHAR, is_founder BOOLEAN,
    parent_id UUID, depth INT, path UUID[]
) AS $$
WITH RECURSIVE descendants AS (
    SELECT
        p.id AS person_id, p.full_name, p.birth_name, p.posthumous_name,
        p.gender::VARCHAR, p.birth_date, p.birth_date_precision, p.birth_date_display,
        p.death_date, p.death_date_precision, p.death_date_display,
        p.birth_place, cm.generation, p.avatar_url,
        cm.role::VARCHAR AS membership_role, COALESCE(cm.is_founder, false) AS is_founder,
        NULL::UUID AS parent_id, 0 AS depth, ARRAY[p.id] AS path
    FROM public.persons p
    LEFT JOIN public.clan_memberships cm ON cm.person_id = p.id AND cm.clan_id = p_clan_id
    WHERE p.id = p_root_id AND p.is_deleted = false

    UNION ALL

    SELECT
        p.id, p.full_name, p.birth_name, p.posthumous_name, p.gender::VARCHAR,
        p.birth_date, p.birth_date_precision, p.birth_date_display,
        p.death_date, p.death_date_precision, p.death_date_display,
        p.birth_place, cm.generation, p.avatar_url, cm.role::VARCHAR AS membership_role,
        COALESCE(cm.is_founder, false) AS is_founder, d.person_id AS parent_id,
        d.depth + 1 AS depth, d.path || p.id AS path
    FROM descendants d
    JOIN public.parent_child pc
        ON pc.parent_id = d.person_id
        AND pc.is_deleted = false
        AND pc.created_by_clan_id = p_clan_id
    JOIN public.persons p ON p.id = pc.child_id AND p.is_deleted = false
    LEFT JOIN public.clan_memberships cm ON cm.person_id = p.id AND cm.clan_id = p_clan_id
    WHERE d.depth < p_max_generations AND NOT (p.id = ANY(d.path))
)
SELECT * FROM descendants ORDER BY depth, generation NULLS LAST, full_name;
$$ LANGUAGE sql STABLE;
"""

_GET_ANCESTORS_FLAT_NEW = """
CREATE FUNCTION public.get_ancestors_flat(
    p_person_id UUID, p_clan_id UUID, p_max_generations INT DEFAULT 10
)
RETURNS TABLE (
    person_id UUID, full_name VARCHAR, gender VARCHAR, birth_date DATE,
    birth_date_precision VARCHAR, birth_date_display VARCHAR,
    death_date DATE, death_date_precision VARCHAR, death_date_display VARCHAR,
    generation SMALLINT, avatar_url VARCHAR, child_id UUID,
    depth INT, path UUID[]
) AS $$
WITH RECURSIVE ancestors AS (
    SELECT
        p.id AS person_id, p.full_name, p.gender::VARCHAR, p.birth_date,
        p.birth_date_precision, p.birth_date_display,
        p.death_date, p.death_date_precision, p.death_date_display,
        cm.generation, p.avatar_url, NULL::UUID AS child_id, 0 AS depth, ARRAY[p.id] AS path
    FROM public.persons p
    LEFT JOIN public.clan_memberships cm ON cm.person_id = p.id AND cm.clan_id = p_clan_id
    WHERE p.id = p_person_id AND p.is_deleted = false

    UNION ALL

    SELECT
        p.id, p.full_name, p.gender::VARCHAR, p.birth_date,
        p.birth_date_precision, p.birth_date_display,
        p.death_date, p.death_date_precision, p.death_date_display,
        cm.generation, p.avatar_url, a.person_id AS child_id, a.depth + 1, a.path || p.id
    FROM ancestors a
    JOIN public.parent_child pc
        ON pc.child_id = a.person_id
        AND pc.is_deleted = false
        AND pc.created_by_clan_id = p_clan_id
    JOIN public.persons p ON p.id = pc.parent_id AND p.is_deleted = false
    LEFT JOIN public.clan_memberships cm ON cm.person_id = p.id AND cm.clan_id = p_clan_id
    WHERE a.depth < p_max_generations AND NOT (p.id = ANY(a.path))
)
SELECT * FROM ancestors ORDER BY depth, full_name;
$$ LANGUAGE sql STABLE;
"""

# --- Migration 005 definitions (restored verbatim on downgrade) --------------------
_GET_FAMILY_TREE_FLAT_005 = """
CREATE FUNCTION public.get_family_tree_flat(
    p_root_id         UUID,
    p_clan_id         UUID,
    p_max_generations INT DEFAULT 10
)
RETURNS TABLE (
    person_id UUID, full_name VARCHAR, birth_name VARCHAR, posthumous_name VARCHAR,
    gender VARCHAR, birth_date DATE, birth_date_approx BOOLEAN, death_date DATE,
    death_date_approx BOOLEAN, birth_place VARCHAR, generation SMALLINT,
    avatar_url VARCHAR, membership_role VARCHAR, is_founder BOOLEAN,
    parent_id UUID, depth INT, path UUID[]
) AS $$
WITH RECURSIVE descendants AS (
    SELECT
        p.id AS person_id, p.full_name, p.birth_name, p.posthumous_name,
        p.gender::VARCHAR, p.birth_date, p.birth_date_approx, p.death_date,
        p.death_date_approx, p.birth_place, cm.generation, p.avatar_url,
        cm.role::VARCHAR AS membership_role, COALESCE(cm.is_founder, false) AS is_founder,
        NULL::UUID AS parent_id, 0 AS depth, ARRAY[p.id] AS path
    FROM public.persons p
    LEFT JOIN public.clan_memberships cm ON cm.person_id = p.id AND cm.clan_id = p_clan_id
    WHERE p.id = p_root_id AND p.is_deleted = false

    UNION ALL

    SELECT
        p.id, p.full_name, p.birth_name, p.posthumous_name, p.gender::VARCHAR,
        p.birth_date, p.birth_date_approx, p.death_date, p.death_date_approx,
        p.birth_place, cm.generation, p.avatar_url, cm.role::VARCHAR AS membership_role,
        COALESCE(cm.is_founder, false) AS is_founder, d.person_id AS parent_id,
        d.depth + 1 AS depth, d.path || p.id AS path
    FROM descendants d
    JOIN public.parent_child pc
        ON pc.parent_id = d.person_id
        AND pc.is_deleted = false
        AND pc.created_by_clan_id = p_clan_id
    JOIN public.persons p ON p.id = pc.child_id AND p.is_deleted = false
    LEFT JOIN public.clan_memberships cm ON cm.person_id = p.id AND cm.clan_id = p_clan_id
    WHERE d.depth < p_max_generations AND NOT (p.id = ANY(d.path))
)
SELECT * FROM descendants ORDER BY depth, generation NULLS LAST, full_name;
$$ LANGUAGE sql STABLE;
"""

_GET_ANCESTORS_FLAT_005 = """
CREATE FUNCTION public.get_ancestors_flat(
    p_person_id UUID, p_clan_id UUID, p_max_generations INT DEFAULT 10
)
RETURNS TABLE (
    person_id UUID, full_name VARCHAR, gender VARCHAR, birth_date DATE,
    death_date DATE, generation SMALLINT, avatar_url VARCHAR, child_id UUID,
    depth INT, path UUID[]
) AS $$
WITH RECURSIVE ancestors AS (
    SELECT
        p.id AS person_id, p.full_name, p.gender::VARCHAR, p.birth_date, p.death_date,
        cm.generation, p.avatar_url, NULL::UUID AS child_id, 0 AS depth, ARRAY[p.id] AS path
    FROM public.persons p
    LEFT JOIN public.clan_memberships cm ON cm.person_id = p.id AND cm.clan_id = p_clan_id
    WHERE p.id = p_person_id AND p.is_deleted = false

    UNION ALL

    SELECT
        p.id, p.full_name, p.gender::VARCHAR, p.birth_date, p.death_date,
        cm.generation, p.avatar_url, a.person_id AS child_id, a.depth + 1, a.path || p.id
    FROM ancestors a
    JOIN public.parent_child pc
        ON pc.child_id = a.person_id
        AND pc.is_deleted = false
        AND pc.created_by_clan_id = p_clan_id
    JOIN public.persons p ON p.id = pc.parent_id AND p.is_deleted = false
    LEFT JOIN public.clan_memberships cm ON cm.person_id = p.id AND cm.clan_id = p_clan_id
    WHERE a.depth < p_max_generations AND NOT (p.id = ANY(a.path))
)
SELECT * FROM ancestors ORDER BY depth, full_name;
$$ LANGUAGE sql STABLE;
"""

_DROP_GET_FAMILY_TREE_FLAT = "DROP FUNCTION public.get_family_tree_flat(UUID, UUID, INT);"
_DROP_GET_ANCESTORS_FLAT = "DROP FUNCTION public.get_ancestors_flat(UUID, UUID, INT);"


def upgrade() -> None:
    op.execute(_DROP_GET_FAMILY_TREE_FLAT)
    op.execute(_GET_FAMILY_TREE_FLAT_NEW)
    op.execute(_DROP_GET_ANCESTORS_FLAT)
    op.execute(_GET_ANCESTORS_FLAT_NEW)


def downgrade() -> None:
    op.execute(_DROP_GET_FAMILY_TREE_FLAT)
    op.execute(_GET_FAMILY_TREE_FLAT_005)
    op.execute(_DROP_GET_ANCESTORS_FLAT)
    op.execute(_GET_ANCESTORS_FLAT_005)
