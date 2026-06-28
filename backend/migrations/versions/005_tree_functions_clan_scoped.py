"""Clan-scope the tree traversal functions by edge ownership (C6/C7).

Migration 003 ported the tree functions verbatim, where the recursive walk over
``parent_child`` / ``marriages`` had no clan predicate (the clan_memberships join
was decorative), so the walk crossed clan boundaries and leaked other clans'
person data (2026-06-28 design review, findings C6/C7).

This replaces the three traversed functions so every edge step is filtered by
``created_by_clan_id = p_clan_id`` — the same edge-ownership rule the relationship
read path already enforces (and that has cross-clan isolation tests). A person who
is not a clan member but whom the clan legitimately recorded an edge for stays
visible (the clan owns the edge); a person reachable only via another clan's edge
is not. The helper functions (get_spouses/get_children/get_parents) are unchanged.

Revision ID: 005_tree_functions_clan_scoped
Revises: 004_fcm_tokens
"""

from __future__ import annotations

from alembic import op

revision: str = "005_tree_functions_clan_scoped"
down_revision: str | None = "004_fcm_tokens"
branch_labels = None
depends_on = None


# --- Clan-scoped definitions (edge created_by_clan_id = p_clan_id) ----------------
_GET_FAMILY_TREE_FLAT_SCOPED = """
CREATE OR REPLACE FUNCTION public.get_family_tree_flat(
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

_GET_ANCESTORS_FLAT_SCOPED = """
CREATE OR REPLACE FUNCTION public.get_ancestors_flat(
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

_FIND_PATH_SCOPED = """
CREATE OR REPLACE FUNCTION public.find_relationship_path(
    p_from_id UUID, p_to_id UUID, p_clan_id UUID, p_max_depth INT DEFAULT 20
)
RETURNS TABLE (
    step INT, person_id UUID, full_name VARCHAR, gender VARCHAR, edge_type VARCHAR
) AS $$
WITH RECURSIVE bfs AS (
    SELECT
        p.id AS current_id, p.full_name, p.gender::VARCHAR, ARRAY[p.id] AS path_ids,
        ARRAY[NULL::VARCHAR] AS path_edges, 0 AS depth
    FROM public.persons p
    WHERE p.id = p_from_id AND p.is_deleted = false

    UNION ALL

    SELECT
        next_p.id, next_p.full_name, next_p.gender::VARCHAR,
        bfs.path_ids || next_p.id, bfs.path_edges || edges.edge_type, bfs.depth + 1
    FROM bfs
    CROSS JOIN LATERAL (
        SELECT pc.parent_id AS neighbor_id, 'parent'::VARCHAR AS edge_type
        FROM public.parent_child pc
        WHERE pc.child_id = bfs.current_id AND pc.is_deleted = false
          AND pc.created_by_clan_id = p_clan_id
        UNION ALL
        SELECT pc.child_id AS neighbor_id, 'child'::VARCHAR AS edge_type
        FROM public.parent_child pc
        WHERE pc.parent_id = bfs.current_id AND pc.is_deleted = false
          AND pc.created_by_clan_id = p_clan_id
        UNION ALL
        SELECT
            CASE WHEN m.person1_id = bfs.current_id THEN m.person2_id
                 ELSE m.person1_id END AS neighbor_id,
            'spouse'::VARCHAR AS edge_type
        FROM public.marriages m
        WHERE (m.person1_id = bfs.current_id OR m.person2_id = bfs.current_id)
          AND m.is_deleted = false
          AND m.created_by_clan_id = p_clan_id
    ) edges
    JOIN public.persons next_p ON next_p.id = edges.neighbor_id AND next_p.is_deleted = false
    WHERE bfs.depth < p_max_depth AND NOT (next_p.id = ANY(bfs.path_ids))
)
SELECT
    gs.step, bfs.path_ids[gs.step + 1] AS person_id, p.full_name, p.gender::VARCHAR,
    bfs.path_edges[gs.step + 1] AS edge_type
FROM bfs
CROSS JOIN LATERAL generate_series(0, array_length(bfs.path_ids, 1) - 1) AS gs(step)
JOIN public.persons p ON p.id = bfs.path_ids[gs.step + 1]
WHERE bfs.current_id = p_to_id
ORDER BY array_length(bfs.path_ids, 1), gs.step
LIMIT (
    SELECT array_length(shortest.path_ids, 1) FROM bfs shortest
    WHERE shortest.current_id = p_to_id
    ORDER BY array_length(shortest.path_ids, 1) LIMIT 1
);
$$ LANGUAGE sql STABLE;
"""

# --- Unscoped definitions (003 originals) for downgrade ---------------------------
_GET_FAMILY_TREE_FLAT_UNSCOPED = _GET_FAMILY_TREE_FLAT_SCOPED.replace(
    "        AND pc.created_by_clan_id = p_clan_id\n", ""
)
_GET_ANCESTORS_FLAT_UNSCOPED = _GET_ANCESTORS_FLAT_SCOPED.replace(
    "        AND pc.created_by_clan_id = p_clan_id\n", ""
)
_FIND_PATH_UNSCOPED = _FIND_PATH_SCOPED.replace(
    "          AND pc.created_by_clan_id = p_clan_id\n", ""
).replace("          AND m.created_by_clan_id = p_clan_id\n", "")


def upgrade() -> None:
    op.execute(_GET_FAMILY_TREE_FLAT_SCOPED)
    op.execute(_GET_ANCESTORS_FLAT_SCOPED)
    op.execute(_FIND_PATH_SCOPED)


def downgrade() -> None:
    op.execute(_GET_FAMILY_TREE_FLAT_UNSCOPED)
    op.execute(_GET_ANCESTORS_FLAT_UNSCOPED)
    op.execute(_FIND_PATH_UNSCOPED)
