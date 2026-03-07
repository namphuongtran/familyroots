-- ============================================================
-- 002_tree_functions.sql
-- SQL functions for family tree traversal
-- Bidirectional spouse lookup, children, parents, and
-- recursive tree/ancestor queries.
-- ============================================================

-- ============================================================
-- FUNCTION: get_spouses(p_member_id, p_clan_id)
-- Returns all spouse records for a member (checks both directions)
-- ============================================================
CREATE OR REPLACE FUNCTION public.get_spouses(
    p_member_id UUID,
    p_clan_id   UUID
)
RETURNS TABLE (
    spouse_id        UUID,
    relation_subtype relation_subtype,
    start_date       DATE,
    end_date         DATE,
    is_primary       BOOLEAN,
    notes            TEXT
) AS $$
    SELECT
        CASE
            WHEN r.member_id = p_member_id THEN r.related_id
            ELSE r.member_id
        END AS spouse_id,
        r.relation_subtype,
        r.start_date,
        r.end_date,
        r.is_primary,
        r.notes
    FROM public.relationships r
    WHERE r.clan_id = p_clan_id
      AND r.relation_type = 'spouse'
      AND (r.member_id = p_member_id OR r.related_id = p_member_id)
    ORDER BY r.is_primary DESC, r.start_date ASC NULLS LAST;
$$ LANGUAGE sql STABLE;

-- ============================================================
-- FUNCTION: get_children(p_member_id, p_clan_id)
-- Returns all children of a member
-- ============================================================
CREATE OR REPLACE FUNCTION public.get_children(
    p_member_id UUID,
    p_clan_id   UUID
)
RETURNS TABLE (
    child_id         UUID,
    relation_subtype relation_subtype,
    other_parent_id  UUID
) AS $$
    SELECT
        r.related_id AS child_id,
        r.relation_subtype,
        -- Find the other parent of this child (if any)
        (
            SELECT r2.member_id
            FROM public.relationships r2
            WHERE r2.related_id = r.related_id
              AND r2.relation_type = 'parent'
              AND r2.clan_id = p_clan_id
              AND r2.member_id != p_member_id
            LIMIT 1
        ) AS other_parent_id
    FROM public.relationships r
    WHERE r.clan_id = p_clan_id
      AND r.relation_type = 'parent'
      AND r.member_id = p_member_id;
$$ LANGUAGE sql STABLE;

-- ============================================================
-- FUNCTION: get_parents(p_member_id, p_clan_id)
-- Returns all parents of a member
-- ============================================================
CREATE OR REPLACE FUNCTION public.get_parents(
    p_member_id UUID,
    p_clan_id   UUID
)
RETURNS TABLE (
    parent_id        UUID,
    relation_subtype relation_subtype
) AS $$
    SELECT
        r.member_id AS parent_id,
        r.relation_subtype
    FROM public.relationships r
    WHERE r.clan_id = p_clan_id
      AND r.relation_type = 'parent'
      AND r.related_id = p_member_id;
$$ LANGUAGE sql STABLE;

-- ============================================================
-- FUNCTION: get_family_tree_flat(p_root_id, p_clan_id, p_max_generations)
-- Returns ALL descendants of root as a flat table.
-- FastAPI then assembles this into a nested JSON tree.
-- Uses WITH RECURSIVE to traverse parent→child edges.
-- Returns members + their relationship context for tree rendering.
-- ============================================================
CREATE OR REPLACE FUNCTION public.get_family_tree_flat(
    p_root_id         UUID,
    p_clan_id         UUID,
    p_max_generations INT DEFAULT 10
)
RETURNS TABLE (
    member_id         UUID,
    full_name         VARCHAR,
    birth_name        VARCHAR,
    gender            gender_type,
    birth_date        DATE,
    birth_date_approx BOOLEAN,
    death_date        DATE,
    death_date_approx BOOLEAN,
    birth_place       VARCHAR,
    generation        SMALLINT,
    avatar_url        VARCHAR,
    is_clan_member    BOOLEAN,
    is_clan_founder   BOOLEAN,
    -- Tree position context
    parent_id         UUID,           -- direct parent in traversal (for tree structure)
    depth             INT,            -- depth from root (0 = root)
    path              UUID[]          -- full path from root (for cycle detection)
) AS $$
WITH RECURSIVE descendants AS (
    -- Base case: root member
    SELECT
        m.id            AS member_id,
        m.full_name,
        m.birth_name,
        m.gender,
        m.birth_date,
        m.birth_date_approx,
        m.death_date,
        m.death_date_approx,
        m.birth_place,
        m.generation,
        m.avatar_url,
        m.is_clan_member,
        m.is_clan_founder,
        NULL::UUID      AS parent_id,
        0               AS depth,
        ARRAY[m.id]     AS path
    FROM public.members m
    WHERE m.id = p_root_id
      AND m.clan_id = p_clan_id
      AND m.is_deleted = false

    UNION ALL

    -- Recursive case: children of current level
    SELECT
        m.id,
        m.full_name,
        m.birth_name,
        m.gender,
        m.birth_date,
        m.birth_date_approx,
        m.death_date,
        m.death_date_approx,
        m.birth_place,
        m.generation,
        m.avatar_url,
        m.is_clan_member,
        m.is_clan_founder,
        d.member_id     AS parent_id,
        d.depth + 1     AS depth,
        d.path || m.id  AS path
    FROM descendants d
    JOIN public.relationships r
        ON r.member_id = d.member_id
        AND r.relation_type = 'parent'
        AND r.clan_id = p_clan_id
    JOIN public.members m
        ON m.id = r.related_id
        AND m.clan_id = p_clan_id
        AND m.is_deleted = false
    WHERE d.depth < p_max_generations
      AND NOT (m.id = ANY(d.path))  -- cycle detection: skip if already visited
)
SELECT * FROM descendants
ORDER BY depth, generation NULLS LAST, full_name;
$$ LANGUAGE sql STABLE;

-- ============================================================
-- FUNCTION: get_ancestors_flat(p_member_id, p_clan_id, p_max_generations)
-- Returns ALL ancestors of a member (going UP the tree).
-- Useful for "find my lineage back to the founder" view.
-- ============================================================
CREATE OR REPLACE FUNCTION public.get_ancestors_flat(
    p_member_id       UUID,
    p_clan_id         UUID,
    p_max_generations INT DEFAULT 10
)
RETURNS TABLE (
    member_id   UUID,
    full_name   VARCHAR,
    gender      gender_type,
    birth_date  DATE,
    death_date  DATE,
    generation  SMALLINT,
    avatar_url  VARCHAR,
    child_id    UUID,        -- the node this ancestor connects down to
    depth       INT,
    path        UUID[]
) AS $$
WITH RECURSIVE ancestors AS (
    -- Base case: the member themselves
    SELECT
        m.id        AS member_id,
        m.full_name,
        m.gender,
        m.birth_date,
        m.death_date,
        m.generation,
        m.avatar_url,
        NULL::UUID  AS child_id,
        0           AS depth,
        ARRAY[m.id] AS path
    FROM public.members m
    WHERE m.id = p_member_id
      AND m.clan_id = p_clan_id
      AND m.is_deleted = false

    UNION ALL

    SELECT
        m.id,
        m.full_name,
        m.gender,
        m.birth_date,
        m.death_date,
        m.generation,
        m.avatar_url,
        a.member_id AS child_id,
        a.depth + 1,
        a.path || m.id
    FROM ancestors a
    JOIN public.relationships r
        ON r.related_id = a.member_id
        AND r.relation_type = 'parent'
        AND r.clan_id = p_clan_id
    JOIN public.members m
        ON m.id = r.member_id
        AND m.clan_id = p_clan_id
        AND m.is_deleted = false
    WHERE a.depth < p_max_generations
      AND NOT (m.id = ANY(a.path))
)
SELECT * FROM ancestors
ORDER BY depth, full_name;
$$ LANGUAGE sql STABLE;
