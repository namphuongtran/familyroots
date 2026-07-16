"""find_relationship_path: frontier BFS with a global visited set (no blow-up).

The 011 body was a recursive CTE expanding parent+child+spouse edges with
only a per-path cycle guard. Family graphs are dense with parallel edges
(a couple linked by both marriage and shared children) and 3-cycles
(father—mother—child), so the number of simple paths grows combinatorially —
one kinship lookup in a pathological-but-realistic graph could materialize
millions of CTE rows and hold a connection for minutes.

This rewrite is a level-by-level BFS over temp tables with a global visited
set: each person is expanded at most once, O(V+E) bounded by clan size.
Signature and returned columns are unchanged, and so is the deterministic
tie-break — keeping the lexicographically-smallest (path_ids, path_edges)
per node at every level yields the same global minimum the 011 ORDER BY
picked, because array comparison is prefix-monotonic.

Revision ID: 019_path_bfs_visited
Revises: 018_query_support_indexes
"""

from __future__ import annotations

from alembic import op

revision: str = "019_path_bfs_visited"
down_revision: str | None = "018_query_support_indexes"
branch_labels = None
depends_on = None

_UPGRADE = """
CREATE OR REPLACE FUNCTION public.find_relationship_path(
    p_from_id UUID, p_to_id UUID, p_clan_id UUID, p_max_depth INT DEFAULT 20
)
RETURNS TABLE (
    step INT, person_id UUID, full_name VARCHAR, gender VARCHAR, edge_type VARCHAR
) AS $$
DECLARE
    v_depth INT := 0;
    v_path_ids UUID[];
    v_path_edges VARCHAR[];
BEGIN
    -- Per-call scratch state. ON COMMIT DROP + IF NOT EXISTS keeps repeated
    -- calls inside one transaction safe; TRUNCATE isolates each call.
    CREATE TEMP TABLE IF NOT EXISTS _frp_visited (
        id UUID PRIMARY KEY, path_ids UUID[], path_edges VARCHAR[]
    ) ON COMMIT DROP;
    CREATE TEMP TABLE IF NOT EXISTS _frp_frontier (
        id UUID PRIMARY KEY, path_ids UUID[], path_edges VARCHAR[]
    ) ON COMMIT DROP;
    TRUNCATE _frp_visited;
    TRUNCATE _frp_frontier;

    INSERT INTO _frp_visited
    SELECT p.id, ARRAY[p.id], ARRAY[NULL::VARCHAR]
    FROM public.persons p
    WHERE p.id = p_from_id AND p.is_deleted = false;
    INSERT INTO _frp_frontier SELECT * FROM _frp_visited;

    WHILE v_depth < p_max_depth
      AND NOT EXISTS (SELECT 1 FROM _frp_visited v WHERE v.id = p_to_id)
      AND EXISTS (SELECT 1 FROM _frp_frontier)
    LOOP
        v_depth := v_depth + 1;

        CREATE TEMP TABLE _frp_next ON COMMIT DROP AS
        WITH expanded AS (
            SELECT edges.neighbor_id,
                   f.path_ids || edges.neighbor_id AS path_ids,
                   f.path_edges || edges.edge_type AS path_edges
            FROM _frp_frontier f
            CROSS JOIN LATERAL (
                SELECT pc.parent_id AS neighbor_id, 'parent'::VARCHAR AS edge_type
                FROM public.parent_child pc
                WHERE pc.child_id = f.id AND pc.is_deleted = false
                  AND pc.created_by_clan_id = p_clan_id
                UNION ALL
                SELECT pc.child_id, 'child'::VARCHAR
                FROM public.parent_child pc
                WHERE pc.parent_id = f.id AND pc.is_deleted = false
                  AND pc.created_by_clan_id = p_clan_id
                UNION ALL
                SELECT CASE WHEN m.person1_id = f.id THEN m.person2_id
                            ELSE m.person1_id END,
                       'spouse'::VARCHAR
                FROM public.marriages m
                WHERE (m.person1_id = f.id OR m.person2_id = f.id)
                  AND m.is_deleted = false
                  AND m.created_by_clan_id = p_clan_id
            ) edges
            JOIN public.persons np
              ON np.id = edges.neighbor_id AND np.is_deleted = false
            WHERE NOT EXISTS (SELECT 1 FROM _frp_visited v WHERE v.id = edges.neighbor_id)
        )
        -- One row per newly-reached person: the lexicographically smallest
        -- (path_ids, path_edges) — the same tie-break 011 applied globally.
        SELECT DISTINCT ON (neighbor_id)
               neighbor_id AS id, expanded.path_ids, expanded.path_edges
        FROM expanded
        ORDER BY neighbor_id, expanded.path_ids, expanded.path_edges;

        TRUNCATE _frp_frontier;
        INSERT INTO _frp_frontier SELECT * FROM _frp_next;
        INSERT INTO _frp_visited SELECT * FROM _frp_next;
        DROP TABLE _frp_next;
    END LOOP;

    SELECT v.path_ids, v.path_edges INTO v_path_ids, v_path_edges
    FROM _frp_visited v WHERE v.id = p_to_id;
    IF v_path_ids IS NULL THEN
        RETURN;
    END IF;

    RETURN QUERY
    SELECT gs.step,
           v_path_ids[gs.step + 1],
           p.full_name,
           p.gender::VARCHAR,
           v_path_edges[gs.step + 1]
    FROM generate_series(0, array_length(v_path_ids, 1) - 1) AS gs(step)
    JOIN public.persons p ON p.id = v_path_ids[gs.step + 1]
    ORDER BY gs.step;
END;
$$ LANGUAGE plpgsql VOLATILE;
"""

_BFS_011 = """
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
"""

_DOWNGRADE = f"""
CREATE OR REPLACE FUNCTION public.find_relationship_path(
    p_from_id UUID, p_to_id UUID, p_clan_id UUID, p_max_depth INT DEFAULT 20
)
RETURNS TABLE (
    step INT, person_id UUID, full_name VARCHAR, gender VARCHAR, edge_type VARCHAR
) AS $$
{_BFS_011},
winner AS (
    SELECT b.path_ids, b.path_edges
    FROM bfs b
    WHERE b.current_id = p_to_id
    ORDER BY array_length(b.path_ids, 1), b.path_ids, b.path_edges
    LIMIT 1
)
SELECT
    gs.step,
    w.path_ids[gs.step + 1] AS person_id,
    p.full_name,
    p.gender::VARCHAR,
    w.path_edges[gs.step + 1] AS edge_type
FROM winner w
CROSS JOIN LATERAL generate_series(0, array_length(w.path_ids, 1) - 1) AS gs(step)
JOIN public.persons p ON p.id = w.path_ids[gs.step + 1]
ORDER BY gs.step;
$$ LANGUAGE sql STABLE;
"""


def upgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.find_relationship_path(UUID, UUID, UUID, INT)")
    op.execute(_UPGRADE)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.find_relationship_path(UUID, UUID, UUID, INT)")
    op.execute(_DOWNGRADE)
