"""DB backstop for genealogy graph invariants (ADR-023).

Max-2-biological-parents and acyclicity were application-layer
SELECT-then-INSERT pre-checks only. Under READ COMMITTED two concurrent
editors adding different "biological fathers" both pass the pre-check and
both commit; concurrent A→B / B→A inserts commit an ancestry cycle. The
spouse_order invariant got its DB backstop in migration 015 — these are the
remaining two invariants the database itself must own, because a corrupt
gia phả graph is worse than a rejected write.

Trigger strategy: AFTER INSERT/UPDATE on parent_child, lock both endpoint
person rows FOR UPDATE in deterministic (LEAST/GREATEST) order — concurrent
writers touching the same persons serialize, so each re-check runs against
the previous writer's committed edges. The count re-check includes the new
row itself (> 2 fails). The cycle walk uses UNION (visited-set semantics)
so it terminates even over already-corrupt data.

Pre-checks fail the migration loudly (listing rows) if existing data already
violates either invariant — no silent repair.

Revision ID: 021_parent_child_guard
Revises: 020_event_soft_delete_occ
"""

from __future__ import annotations

from alembic import op

revision: str = "021_parent_child_guard"
down_revision: str | None = "020_event_soft_delete_occ"
branch_labels = None
depends_on = None

_PRECHECK_BIO = """
DO $$
DECLARE bad TEXT;
BEGIN
    SELECT string_agg(child_id::text, ', ') INTO bad FROM (
        SELECT child_id FROM parent_child
        WHERE relationship_type = 'biological' AND is_deleted = false
        GROUP BY child_id, created_by_clan_id
        HAVING COUNT(*) > 2
    ) v;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'cannot install parent_child guard: children with >2 live biological parents: %', bad;
    END IF;
END $$;
"""

_PRECHECK_CYCLE = """
DO $$
DECLARE bad TEXT;
BEGIN
    WITH RECURSIVE r(start_id, node_id) AS (
        SELECT pc.child_id, pc.parent_id FROM parent_child pc WHERE pc.is_deleted = false
        UNION
        SELECT r.start_id, pc.parent_id
        FROM parent_child pc JOIN r ON pc.child_id = r.node_id
        WHERE pc.is_deleted = false
    )
    SELECT string_agg(DISTINCT start_id::text, ', ') INTO bad
    FROM r WHERE node_id = start_id;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'cannot install parent_child guard: ancestry cycles involving: %', bad;
    END IF;
END $$;
"""

_FUNCTION = """
CREATE OR REPLACE FUNCTION public.parent_child_integrity_guard() RETURNS trigger AS $$
DECLARE
    bio_count INT;
    cycle_found BOOLEAN;
BEGIN
    -- Soft-deleting an edge can never violate either invariant.
    IF NEW.is_deleted THEN
        RETURN NULL;
    END IF;

    IF NEW.parent_id = NEW.child_id THEN
        RAISE EXCEPTION 'relationship_cycle: person % cannot be their own parent', NEW.child_id
            USING ERRCODE = 'check_violation';
    END IF;

    -- Serialize concurrent writers touching these persons (deterministic lock
    -- order avoids deadlocks). After the lock is granted, each SELECT below
    -- runs on a fresh READ COMMITTED snapshot and therefore sees the previous
    -- writer's committed edges — closing the SELECT-then-INSERT race.
    PERFORM 1 FROM public.persons WHERE id = LEAST(NEW.parent_id, NEW.child_id) FOR UPDATE;
    PERFORM 1 FROM public.persons WHERE id = GREATEST(NEW.parent_id, NEW.child_id) FOR UPDATE;

    IF NEW.relationship_type = 'biological' THEN
        SELECT COUNT(*) INTO bio_count
        FROM public.parent_child
        WHERE child_id = NEW.child_id
          AND relationship_type = 'biological'
          AND is_deleted = false
          AND created_by_clan_id = NEW.created_by_clan_id;
        -- The count includes NEW's own row (AFTER trigger).
        IF bio_count > 2 THEN
            RAISE EXCEPTION 'too_many_biological_parents: child % already has 2 live biological parents', NEW.child_id
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    -- parent→child closes a cycle iff child is already an ancestor of parent
    -- (via this clan's live edges). UNION dedupes visited nodes → terminates.
    WITH RECURSIVE anc(id) AS (
        SELECT pc.parent_id FROM public.parent_child pc
        WHERE pc.child_id = NEW.parent_id AND pc.is_deleted = false
          AND pc.created_by_clan_id = NEW.created_by_clan_id
        UNION
        SELECT pc.parent_id FROM public.parent_child pc
        JOIN anc ON pc.child_id = anc.id
        WHERE pc.is_deleted = false AND pc.created_by_clan_id = NEW.created_by_clan_id
    )
    SELECT EXISTS (SELECT 1 FROM anc WHERE anc.id = NEW.child_id) INTO cycle_found;
    IF cycle_found THEN
        RAISE EXCEPTION 'relationship_cycle: edge % -> % closes an ancestry cycle', NEW.parent_id, NEW.child_id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

_TRIGGER = """
CREATE TRIGGER trg_parent_child_integrity
AFTER INSERT OR UPDATE OF parent_id, child_id, relationship_type, is_deleted
ON public.parent_child
FOR EACH ROW EXECUTE FUNCTION public.parent_child_integrity_guard();
"""


def upgrade() -> None:
    op.execute(_PRECHECK_BIO)
    op.execute(_PRECHECK_CYCLE)
    op.execute(_FUNCTION)
    op.execute(_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_parent_child_integrity ON public.parent_child")
    op.execute("DROP FUNCTION IF EXISTS public.parent_child_integrity_guard()")
