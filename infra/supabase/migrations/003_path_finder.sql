-- ============================================================
-- 003_path_finder.sql
-- BFS-based relationship path finder between two persons.
-- Returns the shortest path as a sequence of (person_id, edge_type) steps.
-- Traverses parent_child edges (both directions) and marriage edges.
-- ============================================================

CREATE OR REPLACE FUNCTION public.find_relationship_path(
    p_from_id UUID,
    p_to_id   UUID,
    p_clan_id UUID,
    p_max_depth INT DEFAULT 20
)
RETURNS TABLE (
    step        INT,
    person_id   UUID,
    full_name   VARCHAR,
    gender      VARCHAR,
    edge_type   VARCHAR    -- NULL for the start node, 'parent','child','spouse' for edges
) AS $$
WITH RECURSIVE bfs AS (
    -- Base case: start from p_from_id
    SELECT
        p.id           AS current_id,
        p.full_name,
        p.gender::VARCHAR,
        ARRAY[p.id]    AS path_ids,
        ARRAY[NULL::VARCHAR] AS path_edges,
        0              AS depth
    FROM public.persons p
    WHERE p.id = p_from_id
      AND p.is_deleted = false

    UNION ALL

    -- Recursive: expand parent, child, and spouse edges
    SELECT
        next_p.id,
        next_p.full_name,
        next_p.gender::VARCHAR,
        bfs.path_ids || next_p.id,
        bfs.path_edges || edges.edge_type,
        bfs.depth + 1
    FROM bfs
    CROSS JOIN LATERAL (
        -- Parent edges: current person → their parent
        SELECT pc.parent_id AS neighbor_id, 'parent'::VARCHAR AS edge_type
        FROM public.parent_child pc
        WHERE pc.child_id = bfs.current_id
          AND pc.is_deleted = false

        UNION ALL

        -- Child edges: current person → their child
        SELECT pc.child_id AS neighbor_id, 'child'::VARCHAR AS edge_type
        FROM public.parent_child pc
        WHERE pc.parent_id = bfs.current_id
          AND pc.is_deleted = false

        UNION ALL

        -- Spouse edges (bidirectional via marriages)
        SELECT
            CASE WHEN m.person1_id = bfs.current_id THEN m.person2_id
                 ELSE m.person1_id END AS neighbor_id,
            'spouse'::VARCHAR AS edge_type
        FROM public.marriages m
        WHERE (m.person1_id = bfs.current_id OR m.person2_id = bfs.current_id)
          AND m.is_deleted = false
    ) edges
    JOIN public.persons next_p
        ON next_p.id = edges.neighbor_id
        AND next_p.is_deleted = false
    WHERE bfs.depth < p_max_depth
      AND NOT (next_p.id = ANY(bfs.path_ids))  -- cycle prevention
)
-- Find the path that reaches p_to_id
SELECT
    gs.step,
    bfs.path_ids[gs.step + 1]   AS person_id,
    p.full_name,
    p.gender::VARCHAR,
    bfs.path_edges[gs.step + 1] AS edge_type
FROM bfs
CROSS JOIN LATERAL generate_series(0, array_length(bfs.path_ids, 1) - 1) AS gs(step)
JOIN public.persons p ON p.id = bfs.path_ids[gs.step + 1]
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
