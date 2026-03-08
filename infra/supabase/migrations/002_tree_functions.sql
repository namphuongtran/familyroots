-- ============================================================
-- 002_tree_functions.sql
-- SQL functions for family tree traversal (graph model)
-- Persons are global; edges are marriages + parent_child.
-- Clan context filters via clan_memberships.
-- ============================================================

-- ============================================================
-- FUNCTION: get_spouses(p_person_id, p_clan_id)
-- Returns all spouse records for a person (checks both directions)
-- ============================================================
CREATE OR REPLACE FUNCTION public.get_spouses(
    p_person_id UUID,
    p_clan_id   UUID
)
RETURNS TABLE (
    spouse_id       UUID,
    status          VARCHAR,
    marriage_date   DATE,
    divorce_date    DATE,
    spouse_order    SMALLINT,
    notes           TEXT
) AS $$
    SELECT
        CASE
            WHEN m.person1_id = p_person_id THEN m.person2_id
            ELSE m.person1_id
        END AS spouse_id,
        m.status,
        m.marriage_date,
        m.divorce_date,
        m.spouse_order,
        m.notes
    FROM public.marriages m
    WHERE (m.person1_id = p_person_id OR m.person2_id = p_person_id)
    ORDER BY m.spouse_order ASC NULLS LAST, m.marriage_date ASC NULLS LAST;
$$ LANGUAGE sql STABLE;

-- ============================================================
-- FUNCTION: get_children(p_person_id, p_clan_id)
-- Returns all children of a person
-- ============================================================
CREATE OR REPLACE FUNCTION public.get_children(
    p_person_id UUID,
    p_clan_id   UUID
)
RETURNS TABLE (
    child_id          UUID,
    relationship_type VARCHAR,
    other_parent_id   UUID
) AS $$
    SELECT
        pc.child_id,
        pc.relationship_type,
        -- Find the other parent of this child (if any)
        (
            SELECT pc2.parent_id
            FROM public.parent_child pc2
            WHERE pc2.child_id = pc.child_id
              AND pc2.parent_id != p_person_id
            LIMIT 1
        ) AS other_parent_id
    FROM public.parent_child pc
    WHERE pc.parent_id = p_person_id;
$$ LANGUAGE sql STABLE;

-- ============================================================
-- FUNCTION: get_parents(p_person_id, p_clan_id)
-- Returns all parents of a person
-- ============================================================
CREATE OR REPLACE FUNCTION public.get_parents(
    p_person_id UUID,
    p_clan_id   UUID
)
RETURNS TABLE (
    parent_id         UUID,
    relationship_type VARCHAR
) AS $$
    SELECT
        pc.parent_id,
        pc.relationship_type
    FROM public.parent_child pc
    WHERE pc.child_id = p_person_id;
$$ LANGUAGE sql STABLE;

-- ============================================================
-- FUNCTION: get_family_tree_flat(p_root_id, p_clan_id, p_max_generations)
-- Returns ALL descendants of root as a flat table.
-- FastAPI then assembles this into a nested JSON tree.
-- Uses WITH RECURSIVE to traverse parent→child edges.
-- Clan context provides membership_role and is_founder via clan_memberships.
-- ============================================================
CREATE OR REPLACE FUNCTION public.get_family_tree_flat(
    p_root_id         UUID,
    p_clan_id         UUID,
    p_max_generations INT DEFAULT 10
)
RETURNS TABLE (
    person_id         UUID,
    full_name         VARCHAR,
    birth_name        VARCHAR,
    posthumous_name   VARCHAR,
    gender            VARCHAR,
    birth_date        DATE,
    birth_date_approx BOOLEAN,
    death_date        DATE,
    death_date_approx BOOLEAN,
    birth_place       VARCHAR,
    generation        SMALLINT,
    avatar_url        VARCHAR,
    membership_role   VARCHAR,
    is_founder        BOOLEAN,
    -- Tree position context
    parent_id         UUID,           -- direct parent in traversal (for tree structure)
    depth             INT,            -- depth from root (0 = root)
    path              UUID[]          -- full path from root (for cycle detection)
) AS $$
WITH RECURSIVE descendants AS (
    -- Base case: root person
    SELECT
        p.id            AS person_id,
        p.full_name,
        p.birth_name,
        p.posthumous_name,
        p.gender::VARCHAR,
        p.birth_date,
        p.birth_date_approx,
        p.death_date,
        p.death_date_approx,
        p.birth_place,
        cm.generation,
        p.avatar_url,
        cm.role::VARCHAR AS membership_role,
        COALESCE(cm.is_founder, false) AS is_founder,
        NULL::UUID      AS parent_id,
        0               AS depth,
        ARRAY[p.id]     AS path
    FROM public.persons p
    LEFT JOIN public.clan_memberships cm
        ON cm.person_id = p.id AND cm.clan_id = p_clan_id
    WHERE p.id = p_root_id
      AND p.is_deleted = false

    UNION ALL

    -- Recursive case: children of current level
    SELECT
        p.id,
        p.full_name,
        p.birth_name,
        p.posthumous_name,
        p.gender::VARCHAR,
        p.birth_date,
        p.birth_date_approx,
        p.death_date,
        p.death_date_approx,
        p.birth_place,
        cm.generation,
        p.avatar_url,
        cm.role::VARCHAR AS membership_role,
        COALESCE(cm.is_founder, false) AS is_founder,
        d.person_id     AS parent_id,
        d.depth + 1     AS depth,
        d.path || p.id  AS path
    FROM descendants d
    JOIN public.parent_child pc
        ON pc.parent_id = d.person_id
    JOIN public.persons p
        ON p.id = pc.child_id
        AND p.is_deleted = false
    LEFT JOIN public.clan_memberships cm
        ON cm.person_id = p.id AND cm.clan_id = p_clan_id
    WHERE d.depth < p_max_generations
      AND NOT (p.id = ANY(d.path))  -- cycle detection: skip if already visited
)
SELECT * FROM descendants
ORDER BY depth, generation NULLS LAST, full_name;
$$ LANGUAGE sql STABLE;

-- ============================================================
-- FUNCTION: get_ancestors_flat(p_person_id, p_clan_id, p_max_generations)
-- Returns ALL ancestors of a person (going UP the tree).
-- Useful for "find my lineage back to the founder" view.
-- ============================================================
CREATE OR REPLACE FUNCTION public.get_ancestors_flat(
    p_person_id       UUID,
    p_clan_id         UUID,
    p_max_generations INT DEFAULT 10
)
RETURNS TABLE (
    person_id   UUID,
    full_name   VARCHAR,
    gender      VARCHAR,
    birth_date  DATE,
    death_date  DATE,
    generation  SMALLINT,
    avatar_url  VARCHAR,
    child_id    UUID,        -- the node this ancestor connects down to
    depth       INT,
    path        UUID[]
) AS $$
WITH RECURSIVE ancestors AS (
    -- Base case: the person themselves
    SELECT
        p.id        AS person_id,
        p.full_name,
        p.gender::VARCHAR,
        p.birth_date,
        p.death_date,
        cm.generation,
        p.avatar_url,
        NULL::UUID  AS child_id,
        0           AS depth,
        ARRAY[p.id] AS path
    FROM public.persons p
    LEFT JOIN public.clan_memberships cm
        ON cm.person_id = p.id AND cm.clan_id = p_clan_id
    WHERE p.id = p_person_id
      AND p.is_deleted = false

    UNION ALL

    SELECT
        p.id,
        p.full_name,
        p.gender::VARCHAR,
        p.birth_date,
        p.death_date,
        cm.generation,
        p.avatar_url,
        a.person_id AS child_id,
        a.depth + 1,
        a.path || p.id
    FROM ancestors a
    JOIN public.parent_child pc
        ON pc.child_id = a.person_id
    JOIN public.persons p
        ON p.id = pc.parent_id
        AND p.is_deleted = false
    LEFT JOIN public.clan_memberships cm
        ON cm.person_id = p.id AND cm.clan_id = p_clan_id
    WHERE a.depth < p_max_generations
      AND NOT (p.id = ANY(a.path))
)
SELECT * FROM ancestors
ORDER BY depth, full_name;
$$ LANGUAGE sql STABLE;
