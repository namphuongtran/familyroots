"""find_relationship_path: return ONE deterministic shortest path (tie-break fix).

The 005 version's final SELECT unnested *every* bfs row reaching the target, ordered by
(path length, step), then ``LIMIT shortest_length``. With TWO shortest paths of equal
length (consanguineous marriage, double cousins, full siblings sharing two parents), the
two paths' step rows interleave and ``LIMIT N`` slices a corrupted mixture (e.g. the
source duplicated, the target dropped). The kinship descriptor then labels garbage.

Fix: select ONE whole shortest path in a ``winner`` CTE (ordered by length, then the
path_ids array for a deterministic tie-break), then unnest only that path. Signature and
returned columns are unchanged.

Revision ID: 011_path_tiebreak
Revises: 010_clan_fk_restrict
"""

from __future__ import annotations

from alembic import op

revision: str = "011_path_tiebreak"
down_revision: str | None = "010_clan_fk_restrict"
branch_labels = None
depends_on = None

_BFS = """
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

# Fixed: pick one whole shortest path, then unnest only that path.
_UPGRADE = f"""
CREATE OR REPLACE FUNCTION public.find_relationship_path(
    p_from_id UUID, p_to_id UUID, p_clan_id UUID, p_max_depth INT DEFAULT 20
)
RETURNS TABLE (
    step INT, person_id UUID, full_name VARCHAR, gender VARCHAR, edge_type VARCHAR
) AS $$
{_BFS},
winner AS (
    SELECT b.path_ids, b.path_edges
    FROM bfs b
    WHERE b.current_id = p_to_id
    ORDER BY array_length(b.path_ids, 1), b.path_ids
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

# Original 005 body (interleaves tied shortest paths) — restored on downgrade.
_DOWNGRADE = f"""
CREATE OR REPLACE FUNCTION public.find_relationship_path(
    p_from_id UUID, p_to_id UUID, p_clan_id UUID, p_max_depth INT DEFAULT 20
)
RETURNS TABLE (
    step INT, person_id UUID, full_name VARCHAR, gender VARCHAR, edge_type VARCHAR
) AS $$
{_BFS}
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


def upgrade() -> None:
    op.execute(_UPGRADE)


def downgrade() -> None:
    op.execute(_DOWNGRADE)
