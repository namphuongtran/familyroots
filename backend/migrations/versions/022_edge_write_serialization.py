"""Per-clan edge-write serialization + invariant-matching unique backstops (ADR-025).

H2 (review 2026-07-18): 021's trigger serializes concurrent parent_child writers by
FOR UPDATE-locking the two ENDPOINT persons — writers whose endpoints are disjoint
never serialize, so with committed D→A and B→C, concurrent inserts A→B and C→D both
pass their (pre-race snapshot) cycle walks and COMMIT AN ANCESTRY CYCLE. Fix: a
per-clan pg_advisory_xact_lock at the top of the trigger — the bio-cap count and the
cycle walk are both clan-scoped, so a per-clan critical section makes every writer's
re-check see every earlier writer's committed edges. Two-arg keyspace (classid
728116) cannot collide with the background jobs' one-arg locks 728_115_00x (those
occupy classid 0); hashtext collisions across clans merely over-serialize.

M2a: idx_marriages_unique_pair was partial on status='married', but the app's
"active" (has_active_marriage, and 015's spouse_order index) is status<>'divorced' —
concurrent same-pair widowed/separated creates both landed. Widened; this also
closes tracked race M4 (divorced→active UPDATE now re-checks the index).

M2b: idx_parent_child_unique_edge keyed on relationship_type, but the app forbids
ANY second live link per (parent, child). relationship_type dropped from the key.

Also: CHECK constraints for the five *_precision columns (enum enforced only in
Pydantic until now) and branches self-parenting.

Pre-checks fail the migration loudly (listing rows) if existing data already
violates any widened/new constraint — no silent repair (015/021 precedent).

Revision ID: 022_edge_write_serialization
Revises: 021_parent_child_guard
"""

from __future__ import annotations

from alembic import op

revision: str = "022_edge_write_serialization"
down_revision: str | None = "021_parent_child_guard"
branch_labels = None
depends_on = None

_PRECISION_ENUM = "('exact','year','month','circa','unknown')"

_PRECHECK_MARRIAGE_PAIRS = """
DO $$
DECLARE bad TEXT;
BEGIN
    SELECT string_agg(v.pair, '; ') INTO bad FROM (
        SELECT format('clan=%s pair=%s/%s x%s', created_by_clan_id,
                      LEAST(person1_id, person2_id), GREATEST(person1_id, person2_id),
                      COUNT(*)) AS pair
        FROM marriages
        WHERE status <> 'divorced' AND is_deleted = false
        GROUP BY created_by_clan_id, LEAST(person1_id, person2_id),
                 GREATEST(person1_id, person2_id)
        HAVING COUNT(*) > 1
    ) v;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'cannot widen idx_marriages_unique_pair: pairs with multiple live non-divorced marriages: %', bad;
    END IF;
END $$;
"""

_PRECHECK_EDGE_PAIRS = """
DO $$
DECLARE bad TEXT;
BEGIN
    SELECT string_agg(v.pair, '; ') INTO bad FROM (
        SELECT format('clan=%s edge=%s->%s x%s', created_by_clan_id, parent_id,
                      child_id, COUNT(*)) AS pair
        FROM parent_child
        WHERE is_deleted = false
        GROUP BY created_by_clan_id, parent_id, child_id
        HAVING COUNT(*) > 1
    ) v;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'cannot widen idx_parent_child_unique_edge: pairs with multiple live edges: %', bad;
    END IF;
END $$;
"""

_PRECHECK_PRECISION = f"""
DO $$
DECLARE bad TEXT;
BEGIN
    SELECT string_agg(v.rec, '; ') INTO bad FROM (
        SELECT format('persons.birth %s', id) AS rec FROM persons
          WHERE birth_date_precision NOT IN {_PRECISION_ENUM}
        UNION ALL
        SELECT format('persons.death %s', id) FROM persons
          WHERE death_date_precision NOT IN {_PRECISION_ENUM}
        UNION ALL
        SELECT format('events.event %s', id) FROM events
          WHERE event_date_precision NOT IN {_PRECISION_ENUM}
        UNION ALL
        SELECT format('marriages.marriage %s', id) FROM marriages
          WHERE marriage_date_precision NOT IN {_PRECISION_ENUM}
        UNION ALL
        SELECT format('marriages.divorce %s', id) FROM marriages
          WHERE divorce_date_precision NOT IN {_PRECISION_ENUM}
    ) v;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'cannot add precision CHECKs: rows with out-of-enum precision: %', bad;
    END IF;
END $$;
"""

_PRECHECK_BRANCH_SELF = """
DO $$
DECLARE bad TEXT;
BEGIN
    SELECT string_agg(id::text, ', ') INTO bad FROM branches WHERE parent_branch_id = id;
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'cannot add branch self-parent CHECK: self-parenting branches: %', bad;
    END IF;
END $$;
"""

# The 022 function: identical to 021 except for the advisory-lock block.
_FUNCTION_022 = """
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

    -- Serialize ALL live-edge writes within a clan (ADR-025). The bio-cap count
    -- and the cycle walk below are both clan-scoped, so a per-clan critical
    -- section makes every writer's re-check see every earlier writer's committed
    -- edges — including writers whose edge ENDPOINTS are disjoint, the race the
    -- per-person FOR UPDATE locks cannot close (H2, review 2026-07-18).
    -- xact-scoped: auto-released at commit/rollback. Two-arg keyspace (classid
    -- 728116) cannot collide with the jobs' one-arg locks 728_115_00x (classid 0);
    -- cross-clan hashtext collisions merely over-serialize (harmless at gia-phả
    -- write rates).
    PERFORM pg_advisory_xact_lock(728116, hashtext(NEW.created_by_clan_id::text));

    -- Person-row locks kept: they additionally serialize against the
    -- claim-approval path (which FOR UPDATEs person rows). Same-clan writers are
    -- already serialized by the advisory lock before reaching these; cross-clan
    -- writers take them in deterministic LEAST/GREATEST order — no deadlock.
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

# 021's function body, verbatim (including its comments), for downgrade
# (no advisory lock) — behaviorally identical to 021_parent_child_guard.py::_FUNCTION.
_FUNCTION_021 = """
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

_CHECKS = [
    ("persons", "ck_persons_birth_precision", f"birth_date_precision IN {_PRECISION_ENUM}"),
    ("persons", "ck_persons_death_precision", f"death_date_precision IN {_PRECISION_ENUM}"),
    ("events", "ck_events_event_precision", f"event_date_precision IN {_PRECISION_ENUM}"),
    (
        "marriages",
        "ck_marriages_marriage_precision",
        f"marriage_date_precision IN {_PRECISION_ENUM}",
    ),
    (
        "marriages",
        "ck_marriages_divorce_precision",
        f"divorce_date_precision IN {_PRECISION_ENUM}",
    ),
    (
        "branches",
        "ck_branches_no_self_parent",
        "parent_branch_id IS NULL OR parent_branch_id <> id",
    ),
]


def upgrade() -> None:
    op.execute(_PRECHECK_MARRIAGE_PAIRS)
    op.execute(_PRECHECK_EDGE_PAIRS)
    op.execute(_PRECHECK_PRECISION)
    op.execute(_PRECHECK_BRANCH_SELF)

    op.execute(_FUNCTION_022)

    op.execute("DROP INDEX IF EXISTS idx_marriages_unique_pair")
    op.execute(
        "CREATE UNIQUE INDEX idx_marriages_unique_pair ON marriages "
        "(created_by_clan_id, LEAST(person1_id, person2_id), "
        "GREATEST(person1_id, person2_id)) "
        "WHERE status <> 'divorced' AND is_deleted = false"
    )
    op.execute("DROP INDEX IF EXISTS idx_parent_child_unique_edge")
    op.execute(
        "CREATE UNIQUE INDEX idx_parent_child_unique_edge ON parent_child "
        "(created_by_clan_id, parent_id, child_id) "
        "WHERE is_deleted = false"
    )

    for table, name, expr in _CHECKS:
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expr})")


def downgrade() -> None:
    for table, name, _ in reversed(_CHECKS):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")

    op.execute("DROP INDEX IF EXISTS idx_parent_child_unique_edge")
    op.execute(
        "CREATE UNIQUE INDEX idx_parent_child_unique_edge ON parent_child "
        "(created_by_clan_id, parent_id, child_id, relationship_type) "
        "WHERE is_deleted = false"
    )
    op.execute("DROP INDEX IF EXISTS idx_marriages_unique_pair")
    op.execute(
        "CREATE UNIQUE INDEX idx_marriages_unique_pair ON marriages "
        "(created_by_clan_id, LEAST(person1_id, person2_id), "
        "GREATEST(person1_id, person2_id), status) "
        "WHERE status = 'married' AND is_deleted = false"
    )

    op.execute(_FUNCTION_021)
