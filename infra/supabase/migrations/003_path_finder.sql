-- ============================================================
-- 003_path_finder.sql
-- BFS-based relationship path finder between two members.
-- Returns the shortest path as a sequence of (member_id, edge_type) steps.
-- ============================================================

CREATE OR REPLACE FUNCTION public.find_relationship_path(
    p_from_id UUID,
    p_to_id   UUID,
    p_clan_id UUID,
    p_max_depth INT DEFAULT 20
)
RETURNS TABLE (
    step        INT,
    member_id   UUID,
    full_name   VARCHAR,
    gender      VARCHAR,
    edge_type   VARCHAR    -- NULL for the start node, 'parent','child','spouse' for edges
) AS $$
WITH RECURSIVE bfs AS (
    -- Base case: start from p_from_id
    SELECT
        m.id           AS current_id,
        m.full_name,
        m.gender::VARCHAR,
        ARRAY[m.id]    AS path_ids,
        ARRAY[NULL::VARCHAR] AS path_edges,
        0              AS depth
    FROM public.members m
    WHERE m.id = p_from_id
      AND m.clan_id = p_clan_id
      AND m.is_deleted = false

    UNION ALL

    -- Recursive: expand parent, child, and spouse edges
    SELECT
        next_m.id,
        next_m.full_name,
        next_m.gender::VARCHAR,
        bfs.path_ids || next_m.id,
        bfs.path_edges || edges.edge_type,
        bfs.depth + 1
    FROM bfs
    CROSS JOIN LATERAL (
        -- Parent edges: current member → their parent
        SELECT r.member_id AS neighbor_id, 'parent'::VARCHAR AS edge_type
        FROM public.relationships r
        WHERE r.related_id = bfs.current_id
          AND r.relation_type = 'parent'
          AND r.clan_id = p_clan_id

        UNION ALL

        -- Child edges: current member → their child
        SELECT r.related_id AS neighbor_id, 'child'::VARCHAR AS edge_type
        FROM public.relationships r
        WHERE r.member_id = bfs.current_id
          AND r.relation_type = 'parent'
          AND r.clan_id = p_clan_id

        UNION ALL

        -- Spouse edges (bidirectional)
        SELECT
            CASE WHEN r.member_id = bfs.current_id THEN r.related_id
                 ELSE r.member_id END AS neighbor_id,
            'spouse'::VARCHAR AS edge_type
        FROM public.relationships r
        WHERE r.relation_type = 'spouse'
          AND r.clan_id = p_clan_id
          AND (r.member_id = bfs.current_id OR r.related_id = bfs.current_id)
    ) edges
    JOIN public.members next_m
        ON next_m.id = edges.neighbor_id
        AND next_m.clan_id = p_clan_id
        AND next_m.is_deleted = false
    WHERE bfs.depth < p_max_depth
      AND NOT (next_m.id = ANY(bfs.path_ids))  -- cycle prevention
)
-- Find the path that reaches p_to_id
SELECT
    gs.step,
    bfs.path_ids[gs.step + 1]   AS member_id,
    m.full_name,
    m.gender::VARCHAR,
    bfs.path_edges[gs.step + 1] AS edge_type
FROM bfs
CROSS JOIN LATERAL generate_series(0, array_length(bfs.path_ids, 1) - 1) AS gs(step)
JOIN public.members m ON m.id = bfs.path_ids[gs.step + 1]
WHERE bfs.current_id = p_to_id
ORDER BY array_length(bfs.path_ids, 1), gs.step
LIMIT (
    SELECT array_length(shortest.path_ids, 1)
    FROM bfs shortest
    WHERE shortest.current_id = p_to_id
    ORDER BY array_length(shortest.path_ids, 1)
    LIMIT 1
);
$$ LANGUAGE sql STABLE;
