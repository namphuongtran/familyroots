"""Tree-traversal SQL functions (graph model): descendants, ancestors, path-finder.

The tree read path (app/services/tree_builder.py, app/infrastructure/persistence/
tree_repository.py) and relationship cycle detection (relationship_repository.py,
relationship_validator.py) call PostgreSQL set-returning functions that were only
ever defined in the parallel hand-written ``infra/supabase/migrations/{002,003}``
SQL — never in the Alembic chain that ``alembic upgrade head`` actually runs. On a
freshly-migrated database every tree endpoint and cycle check raised
``UndefinedFunction`` (42883). This migration ports those proven definitions
verbatim into Alembic so the Alembic-managed schema is self-contained.

NOTE (deferred to the tenant-isolation phase): ``get_family_tree_flat`` and
``get_ancestors_flat`` join ``clan_memberships`` only to *decorate* generation /
membership_role / is_founder (LEFT JOIN) and walk ``parent_child`` with no clan
predicate, so the recursive walk can cross clan boundaries (see the 2026-06-28
backend design review, findings C6/C7). Porting them here restores functionality
that is currently 100% broken; clan-scoping the recursive walk is the next phase's
work and must land with its own cross-clan exclusion tests before the tree API is
exposed to multiple clans' data.

Revision ID: 003_tree_functions
Revises: 002_rls_documents_pilot
"""

from __future__ import annotations

from alembic import op

revision: str = "003_tree_functions"
down_revision: str | None = "002_rls_documents_pilot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # get_spouses(p_person_id, p_clan_id)
    op.execute(
        """
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
              AND m.is_deleted = false
            ORDER BY m.spouse_order ASC NULLS LAST, m.marriage_date ASC NULLS LAST;
        $$ LANGUAGE sql STABLE;
        """
    )

    # get_children(p_person_id, p_clan_id)
    op.execute(
        """
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
                (
                    SELECT pc2.parent_id
                    FROM public.parent_child pc2
                    WHERE pc2.child_id = pc.child_id
                      AND pc2.parent_id != p_person_id
                      AND pc2.is_deleted = false
                    LIMIT 1
                ) AS other_parent_id
            FROM public.parent_child pc
            WHERE pc.parent_id = p_person_id
              AND pc.is_deleted = false;
        $$ LANGUAGE sql STABLE;
        """
    )

    # get_parents(p_person_id, p_clan_id)
    op.execute(
        """
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
            WHERE pc.child_id = p_person_id
              AND pc.is_deleted = false;
        $$ LANGUAGE sql STABLE;
        """
    )

    # get_family_tree_flat(p_root_id, p_clan_id, p_max_generations)
    op.execute(
        """
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
            parent_id         UUID,
            depth             INT,
            path              UUID[]
        ) AS $$
        WITH RECURSIVE descendants AS (
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
                AND pc.is_deleted = false
            JOIN public.persons p
                ON p.id = pc.child_id
                AND p.is_deleted = false
            LEFT JOIN public.clan_memberships cm
                ON cm.person_id = p.id AND cm.clan_id = p_clan_id
            WHERE d.depth < p_max_generations
              AND NOT (p.id = ANY(d.path))
        )
        SELECT * FROM descendants
        ORDER BY depth, generation NULLS LAST, full_name;
        $$ LANGUAGE sql STABLE;
        """
    )

    # get_ancestors_flat(p_person_id, p_clan_id, p_max_generations)
    op.execute(
        """
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
            child_id    UUID,
            depth       INT,
            path        UUID[]
        ) AS $$
        WITH RECURSIVE ancestors AS (
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
                AND pc.is_deleted = false
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
        """
    )

    # find_relationship_path(p_from_id, p_to_id, p_clan_id, p_max_depth)
    op.execute(
        """
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
            edge_type   VARCHAR
        ) AS $$
        WITH RECURSIVE bfs AS (
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

            SELECT
                next_p.id,
                next_p.full_name,
                next_p.gender::VARCHAR,
                bfs.path_ids || next_p.id,
                bfs.path_edges || edges.edge_type,
                bfs.depth + 1
            FROM bfs
            CROSS JOIN LATERAL (
                SELECT pc.parent_id AS neighbor_id, 'parent'::VARCHAR AS edge_type
                FROM public.parent_child pc
                WHERE pc.child_id = bfs.current_id
                  AND pc.is_deleted = false

                UNION ALL

                SELECT pc.child_id AS neighbor_id, 'child'::VARCHAR AS edge_type
                FROM public.parent_child pc
                WHERE pc.parent_id = bfs.current_id
                  AND pc.is_deleted = false

                UNION ALL

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
              AND NOT (next_p.id = ANY(bfs.path_ids))
        )
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
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.find_relationship_path(UUID, UUID, UUID, INT)")
    op.execute("DROP FUNCTION IF EXISTS public.get_ancestors_flat(UUID, UUID, INT)")
    op.execute("DROP FUNCTION IF EXISTS public.get_family_tree_flat(UUID, UUID, INT)")
    op.execute("DROP FUNCTION IF EXISTS public.get_parents(UUID, UUID)")
    op.execute("DROP FUNCTION IF EXISTS public.get_children(UUID, UUID)")
    op.execute("DROP FUNCTION IF EXISTS public.get_spouses(UUID, UUID)")
