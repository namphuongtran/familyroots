"""find_relationship_path: exclude divorced marriages from spouse edges (M8).

The 019 frontier-BFS body expanded a ``spouse`` edge from every non-deleted
marriage with no status filter, so ``relationship_descriptor`` — which resolves a
kinship term purely from the edge sequence — emitted present-tense "Vợ/Chồng",
"Mẹ kế/Bố dượng", con dâu/rể, and affinal in-law terms for LONG-DIVORCED marriages.

This replaces the function with the identical 019 body plus a single
``AND m.status <> 'divorced'`` on the spouse-edge subquery. Divorced marriages stop
being kinship edges; widowed/separated/married still traverse — matching the
system-wide ``has_active_marriage`` convention (``status <> 'divorced'`` used by the
marriage-uniqueness index in 022, the spouse_order index in 015, and
``relationship_repository``). ``marriages.status`` is NOT NULL (defaults 'married'),
so ``<> 'divorced'`` needs no NULL guard. No schema change; cleanly reversible.

Revision ID: 024_kinship_exclude_divorced
Revises: 023_one_founder_per_clan
"""

from __future__ import annotations

from alembic import op

revision: str = "024_kinship_exclude_divorced"
down_revision: str | None = "023_one_founder_per_clan"
branch_labels = None
depends_on = None

# 019's frontier-BFS body verbatim, with the one added spouse-edge status filter.
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
                  AND m.status <> 'divorced'
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

# 019's frontier-BFS body verbatim (no status filter) — restores the exact prior fn.
_DOWNGRADE = """
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


def upgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.find_relationship_path(UUID, UUID, UUID, INT)")
    op.execute(_UPGRADE)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.find_relationship_path(UUID, UUID, UUID, INT)")
    op.execute(_DOWNGRADE)
