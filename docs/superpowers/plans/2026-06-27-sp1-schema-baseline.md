# SP-1: Schema Baseline & Data-Model Correctness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `alembic upgrade head` build a PostgreSQL schema that matches the ORM models exactly, so the FamilyRoots backend boots and runs core flows without column/FK drift.

**Architecture:** The database is empty and may be reset freely, so we keep the single hand-crafted baseline migration `migrations/versions/001_initial.py` (which contains valuable Vietnamese full-text-search SQL, triggers, and partial indexes) and **surgically edit** the specific drift points rather than regenerating from scratch. Models are the source of truth; the migration is reconciled to them. Verification is a new DB-backed test that runs the migration against a real Postgres and asserts schema correctness + an autogenerate diff with no table/column/FK changes.

**Tech Stack:** Python 3.14, SQLAlchemy 2.0 (async), Alembic, PostgreSQL 18, pytest + pytest-asyncio, `uv` for deps, Docker Compose for local Postgres.

## Global Constraints

- Python `>=3.14`; line length 100; ruff lint selectors per `pyproject.toml`.
- Domain layer stays framework-agnostic; this SP touches only `app/models/*` (ORM), `migrations/*`, and `tests/*` — no domain/application changes.
- Migrations run on the **sync** driver: `migrations/env.py` strips `+asyncpg` from `DATABASE_URL`.
- Enum-valued columns are represented as `String` + `CHECK` (NOT PostgreSQL `ENUM`). The domain layer remains the authority on allowed values.
- Soft-deleted aggregates (Person, Marriage, ParentChild) must never be destroyable by FK cascade — person references use `ON DELETE RESTRICT`.
- Run tests with `uv run pytest`; lint with `uvx ruff check .`; migrations with `uv run alembic ...`.
- Local Postgres for tests: `docker compose up -d pgdb` (service `pgdb`, Postgres 18).

---

## Files

- Modify: `backend/app/models/base.py` — add `naming_convention`; update mixin docstring.
- Modify: `backend/app/models/marriage.py` — person FKs → `RESTRICT`; add gender/status CHECK already present (status CHECK lives in migration).
- Modify: `backend/app/models/parent_child.py` — person FKs → `RESTRICT`.
- Modify: `backend/app/models/clan_invitation.py` — add `status`, `accepted_by`; add partial unique pending index.
- Modify: `backend/migrations/env.py` — explicit `import app.models`; add `include_object` hook.
- Modify: `backend/migrations/versions/001_initial.py` — fix column drift, enum→String+CHECK, FK RESTRICT, invitation columns, `downgrade()` completeness.
- Create: `backend/tests/integration/__init__.py`
- Create: `backend/tests/integration/conftest.py` — real-DB migration fixture.
- Create: `backend/tests/integration/test_schema_baseline.py` — schema-correctness + round-trip + autogen-diff tests.

---

## Task 1: Add metadata naming convention to the declarative base

**Files:**
- Modify: `backend/app/models/base.py`

**Interfaces:**
- Produces: `Base.metadata` carries a standard Alembic naming convention; existing explicitly-named constraints are unaffected. No symbol renames.

- [ ] **Step 1: Edit `base.py` to add the naming convention**

Replace the imports and `Base` class (lines 1–14) with:

```python
"""Declarative base and shared mixins for SQLAlchemy models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Standard Alembic naming convention so future autogenerate runs produce stable,
# predictable constraint/index names. Constraints that are explicitly named in
# models or the baseline migration keep their given names.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

- [ ] **Step 2: Update the `ClanScopedMixin` docstring to drop the false RLS claim**

Replace the `ClanScopedMixin` docstring (the lines describing RLS) with:

```python
class ClanScopedMixin(TimestampMixin):
    """Mixin for all tables that belong to a specific clan.

    Every query against these tables MUST include a clan_id filter. Clan
    isolation is enforced in the application layer (the repository contract);
    a database-level RLS layer is a planned defense-in-depth addition (SP-3),
    not yet active.
    """
```

- [ ] **Step 3: Verify it imports cleanly**

Run: `cd backend && uv run python -c "from app.models.base import Base; print(type(Base.metadata.naming_convention))"`
Expected: prints `<class 'dict'>` (or `immutabledict`), no import error.

- [ ] **Step 4: Lint**

Run: `cd backend && uvx ruff check app/models/base.py`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/base.py
git commit -m "refactor(models): add metadata naming convention; drop false RLS claim in mixin"
```

---

## Task 2: Make migration model import explicit and add autogenerate `include_object`

**Files:**
- Modify: `backend/migrations/env.py`

**Interfaces:**
- Produces: `target_metadata` registers all 18 model tables; autogenerate ignores indexes, check constraints, and the `f_unaccent` function (these are maintained as raw SQL in the baseline). Consumed by Task 9's autogen-diff test.

- [ ] **Step 1: Read the current `env.py` import block and replace it**

Replace the model import block (currently `from app.models import ( ...explicit list... )` at lines 13–25) with a single package import so every table is registered and intent is unambiguous:

```python
import app.models  # noqa: F401 — registers all ORM tables on Base.metadata
from app.models.base import Base
```

- [ ] **Step 2: Add an `include_object` hook so autogenerate compares only tables/columns/FKs/unique constraints**

Find where `context.configure(...)` is called for online mode (inside `run_migrations_online`). Add this function above it and pass `include_object=include_object` to **both** `context.configure(...)` calls (offline and online):

```python
def include_object(object_, name, type_, reflected, compare_to):
    """Limit autogenerate to tables/columns/FKs/unique constraints.

    Indexes (incl. expression/partial/trigram), check constraints, and the
    f_unaccent function are maintained as raw SQL in the baseline migration and
    are not reliably round-tripped by autogenerate, so we exclude them from the
    diff. This keeps the autogen-diff regression test meaningful.
    """
    if type_ in ("index", "check_constraint"):
        return False
    return True
```

- [ ] **Step 3: Verify env.py parses (do NOT import it — env.py runs Alembic context at module top-level)**

Run: `cd backend && uv run python -c "import ast; ast.parse(open('migrations/env.py').read()); print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/env.py
git commit -m "chore(migrations): import full model package; scope autogenerate to tables/columns/FKs"
```

---

## Task 3: Fix column-name drift (persons + identity_claims)

**Files:**
- Modify: `backend/migrations/versions/001_initial.py:69` (persons column), `:138-140` (persons partial index), `:760` (identity_claims column)

**Interfaces:**
- Produces: migration column `persons.created_by_clan_id` and `identity_claims.reviewer_note` — matching `app/models/person.py:20` and `app/models/identity_claim.py:42`. Consumed by Task 9 tests.

- [ ] **Step 1: Rename the persons origin column**

In `001_initial.py`, change the persons column definition (lines 68–73) from:

```python
        sa.Column(
            "origin_clan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clans.id", ondelete="SET NULL"),
            nullable=True,
        ),
```

to:

```python
        sa.Column(
            "created_by_clan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clans.id", ondelete="SET NULL"),
            nullable=True,
        ),
```

- [ ] **Step 2: Update the persons partial index that referenced the old name**

Change the index block (lines 138–141) from:

```python
    op.execute(
        "CREATE INDEX idx_persons_origin_clan ON persons "
        "(origin_clan_id) WHERE origin_clan_id IS NOT NULL"
    )
```

to:

```python
    op.execute(
        "CREATE INDEX idx_persons_created_by_clan ON persons "
        "(created_by_clan_id) WHERE created_by_clan_id IS NOT NULL"
    )
```

- [ ] **Step 3: Rename the identity_claims note column**

Change line 760 from:

```python
        sa.Column("reasoning", sa.Text, nullable=True),
```

to:

```python
        sa.Column("reviewer_note", sa.Text, nullable=True),
```

(Leave the existing `requester_note` column at line 759 untouched — it already matches the model.)

- [ ] **Step 4: Confirm no other references to the old names remain in the migration**

Run: `cd backend && grep -n "origin_clan_id\|reasoning" migrations/versions/001_initial.py`
Expected: **no output** (zero matches).

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/versions/001_initial.py
git commit -m "fix(migrations): align persons/identity_claims column names with models"
```

---

## Task 4: Replace PostgreSQL ENUM types with String + CHECK

**Files:**
- Modify: `backend/migrations/versions/001_initial.py` (5 enum columns at ~l.82, ~l.443, ~l.507, ~l.700, ~l.897; downgrade DROP TYPE at l.991–995)
- Modify: `backend/app/models/marriage.py` (no enum, skip), `backend/app/models/parent_child.py` (no enum, skip) — model CHECK additions are in Step 6 below for the enum-bearing models.

**Interfaces:**
- Produces: columns `persons.gender`, `documents.document_type`, `events.event_type`, `user_clan_roles.role`, `notification_log.status` become `String` with a named `CHECK`, matching the `String` declarations already in the models. No PG enum types remain.

- [ ] **Step 1: Convert `persons.gender` (worked example)**

In `001_initial.py`, change the gender column (lines 80–85) from:

```python
        sa.Column(
            "gender",
            sa.Enum("male", "female", "unknown", name="gender_type", create_type=True),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
```

to:

```python
        sa.Column(
            "gender",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
```

and add this CHECK to the `persons` table's constraint list (next to `persons_death_after_birth` at line 130):

```python
        sa.CheckConstraint(
            "gender IN ('male', 'female', 'unknown')",
            name="persons_gender_check",
        ),
```

- [ ] **Step 2: Convert the remaining four enum columns using the same pattern**

For each, read the `sa.Enum(...)` block (locate with `grep -n "sa.Enum" migrations/versions/001_initial.py`), replace the `sa.Enum(<values>, name=..., create_type=True)` with the `String` length below, and add the matching `sa.CheckConstraint(...)` to that table's constraint list:

- `documents.document_type` → `sa.String(20)`, add:
  ```python
        sa.CheckConstraint(
            "document_type IN ('photo', 'id_document', 'certificate', 'audio', 'video', 'other')",
            name="documents_type_check",
        ),
  ```
- `events.event_type` → `sa.String(30)`, add:
  ```python
        sa.CheckConstraint(
            "event_type IN ('death_anniversary', 'birthday', 'wedding_anniversary', "
            "'clan_ceremony', 'custom')",
            name="events_type_check",
        ),
  ```
- `user_clan_roles.role` → `sa.String(20)`, add:
  ```python
        sa.CheckConstraint(
            "role IN ('admin', 'editor', 'viewer')",
            name="user_clan_roles_role_check",
        ),
  ```
- `notification_log.status` → `sa.String(20)`, add:
  ```python
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')",
            name="notification_log_status_check",
        ),
  ```

Preserve each column's existing `nullable`/`server_default`. Confirm the String length matches the model (`grep -n "document_type\|event_type" app/models/document.py app/models/event.py`; `grep -n "role" app/models/user_clan_role.py`; `grep -n "status" app/models/notification_log.py`). If a model uses a different length, match the model.

- [ ] **Step 3: Remove the enum drops from `downgrade()`**

Delete the five lines at 991–995 of `001_initial.py`:

```python
    op.execute("DROP TYPE IF EXISTS notification_status")
    op.execute("DROP TYPE IF EXISTS document_type")
    op.execute("DROP TYPE IF EXISTS event_type")
    op.execute("DROP TYPE IF EXISTS clan_role")
    op.execute("DROP TYPE IF EXISTS gender_type")
```

(Keep the `# Drop enums` comment removal too, and keep the `f_unaccent` drop at line 998.)

- [ ] **Step 4: Confirm no enum usage remains**

Run: `cd backend && grep -n "sa.Enum\|DROP TYPE\|create_type" migrations/versions/001_initial.py`
Expected: **no output**.

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/versions/001_initial.py
git commit -m "fix(migrations): represent enum columns as String + CHECK (no PG enum types)"
```

---

## Task 5: Change person foreign keys on edges to ON DELETE RESTRICT

**Files:**
- Modify: `backend/app/models/marriage.py:20-29` (person1_id, person2_id)
- Modify: `backend/app/models/parent_child.py:31-40` (parent_id, child_id)
- Modify: `backend/migrations/versions/001_initial.py` (marriages person1/person2 FKs ~l.278-286; parent_child parent/child FKs l.355-366)

**Interfaces:**
- Produces: `marriages.person1_id/person2_id` and `parent_child.parent_id/child_id` FKs use `ondelete="RESTRICT"`. Lineage edges cannot be destroyed by a hard person delete (persons are soft-deleted, ADR-006).

- [ ] **Step 1: Model — marriage person FKs**

In `marriage.py`, change both person FKs (lines 20–29) from `ondelete="CASCADE"` to `ondelete="RESTRICT"`:

```python
    person1_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="RESTRICT"),
        index=True,
    )
    person2_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="RESTRICT"),
        index=True,
    )
```

(Leave `created_by_clan_id` FK to `clans` as `CASCADE` — deleting a clan removes the edges it manages.)

- [ ] **Step 2: Model — parent_child person FKs**

In `parent_child.py`, change both person FKs (lines 31–40) from `ondelete="CASCADE"` to `ondelete="RESTRICT"`:

```python
    parent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="RESTRICT"),
        index=True,
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("persons.id", ondelete="RESTRICT"),
        index=True,
    )
```

- [ ] **Step 3: Migration — marriages person FKs**

In `001_initial.py`, in the `marriages` table, change the `person1_id` and `person2_id` columns' `sa.ForeignKey("persons.id", ondelete="CASCADE")` to `ondelete="RESTRICT"` (person1_id is just above line 283; person2_id is at lines 283–286). Leave `created_by_clan_id` (l.291) as CASCADE.

- [ ] **Step 4: Migration — parent_child person FKs**

In the `parent_child` table, change `parent_id` (l.358) and `child_id` (l.364) `sa.ForeignKey("persons.id", ondelete="CASCADE")` to `ondelete="RESTRICT"`. Leave `created_by_clan_id` (l.370) as CASCADE.

- [ ] **Step 5: Confirm person FKs are RESTRICT and clan FKs remain CASCADE**

Run: `cd backend && grep -n 'persons.id", ondelete' migrations/versions/001_initial.py`
Expected: the marriages and parent_child person FK lines show `ondelete="RESTRICT"`; `user_profiles.person_id` and `identity_claims.person_id` keep their own (`SET NULL` / `CASCADE`) — only the four edge FKs change.

- [ ] **Step 6: Lint**

Run: `cd backend && uvx ruff check app/models/marriage.py app/models/parent_child.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/marriage.py backend/app/models/parent_child.py backend/migrations/versions/001_initial.py
git commit -m "fix(schema): person FKs on edges use ON DELETE RESTRICT (soft-delete safety)"
```

---

## Task 6: Invitation schema — add status + accepted_by + pending uniqueness

**Files:**
- Modify: `backend/app/models/clan_invitation.py`
- Modify: `backend/migrations/versions/001_initial.py` (clan_invitations table ~l.660–690)

**Interfaces:**
- Produces: `clan_invitations.status` (`pending`|`accepted`|`revoked`|`expired`, default `pending`), `clan_invitations.accepted_by` (nullable UUID), and a partial unique index `uq_clan_invitations_pending` guaranteeing at most one `pending` invite per `(clan_id, email)`. Consumed by SP-2's invitation feature.

- [ ] **Step 1: Model — add columns and the pending-unique index**

In `clan_invitation.py`, update `__table_args__` and add the two columns. Replace `__table_args__` (line 15) with:

```python
    __table_args__ = (
        Index("ix_clan_invitations_clan_email", "clan_id", "email"),
        Index(
            "uq_clan_invitations_pending",
            "clan_id",
            "email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )
```

Add `text` to the imports on line 6:

```python
from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
```

Add the two columns after `role` (line 24):

```python
    status: Mapped[str] = mapped_column(String(20), default="pending")
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
```

- [ ] **Step 2: Migration — add columns + CHECK + partial unique index**

In `001_initial.py`, inside the `clan_invitations` `create_table`, add after the `role` column:

```python
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("accepted_by", UUID(as_uuid=True), nullable=True),
```

Add a CHECK to the same table's constraint list:

```python
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="clan_invitations_status_check",
        ),
```

After the existing `op.create_index("ix_clan_invitations_clan_id", ...)` line, add:

```python
    op.execute(
        "CREATE UNIQUE INDEX uq_clan_invitations_pending "
        "ON clan_invitations (clan_id, email) WHERE status = 'pending'"
    )
```

- [ ] **Step 3: Lint**

Run: `cd backend && uvx ruff check app/models/clan_invitation.py`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/clan_invitation.py backend/migrations/versions/001_initial.py
git commit -m "feat(schema): clan_invitations status/accepted_by + one-pending-per-email index"
```

---

## Task 7: Fix `downgrade()` completeness

**Files:**
- Modify: `backend/migrations/versions/001_initial.py:972-988` (downgrade table drops)

**Interfaces:**
- Produces: `downgrade()` drops every table created by `upgrade()`, in reverse-dependency order, so `downgrade base` → `upgrade head` round-trips. Consumed by Task 9 round-trip test.

- [ ] **Step 1: Add the missing `identity_claims` drop**

`identity_claims` is created in `upgrade()` (l.736) but never dropped. In `downgrade()`, add it to the drop list **before** `user_profiles` and `persons` are dropped (it FKs to both). Insert after `op.drop_table("change_requests")` (l.975):

```python
    op.drop_table("identity_claims")
```

- [ ] **Step 2: Verify drop order has no dangling FK dependency**

Run: `cd backend && grep -n "op.drop_table" migrations/versions/001_initial.py`
Expected: `identity_claims` appears before both `user_profiles` and `persons`; all 17 tables created in `upgrade()` are present in the drop list. Cross-check the created tables:
Run: `cd backend && grep -c "op.create_table" migrations/versions/001_initial.py` and `grep -c "op.drop_table" migrations/versions/001_initial.py`
Expected: both counts are equal.

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/versions/001_initial.py
git commit -m "fix(migrations): downgrade() drops identity_claims; complete round-trip"
```

---

## Task 8: DB-backed test fixture for migrations

**Files:**
- Create: `backend/tests/integration/__init__.py`
- Create: `backend/tests/integration/conftest.py`

**Interfaces:**
- Produces: a `migrated_db_url` fixture (session-scoped) that creates a throwaway test database, runs `alembic upgrade head` against it, and yields the sync DSN; and a `sync_engine` fixture yielding a connected SQLAlchemy engine. Consumed by Task 9.

- [ ] **Step 1: Create the package marker**

Create `backend/tests/integration/__init__.py` with a single newline (empty file).

- [ ] **Step 2: Write the fixture**

Create `backend/tests/integration/conftest.py`:

```python
"""Integration-test fixtures that run the real Alembic migration against Postgres.

Requires a running Postgres (see backend/docker-compose: `docker compose up -d pgdb`).
Override the admin DSN via TEST_PG_ADMIN_URL if your local Postgres differs.
"""

import os
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

# Admin connection used to CREATE/DROP the throwaway test database.
ADMIN_URL = os.environ.get(
    "TEST_PG_ADMIN_URL", "postgresql+psycopg2://postgres:password@localhost:5432/postgres"
)
TEST_DB_NAME = "family_roots_schema_test"


def _sync_dsn(db_name: str) -> str:
    base = ADMIN_URL.rsplit("/", 1)[0]
    return f"{base}/{db_name}"


@pytest.fixture(scope="session")
def migrated_db_url() -> Iterator[str]:
    admin = sa.create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
        conn.execute(sa.text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin.dispose()

    test_dsn = _sync_dsn(TEST_DB_NAME)
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    # env.py strips +asyncpg; pass the sync DSN directly.
    cfg.set_main_option("sqlalchemy.url", test_dsn)
    os.environ["DATABASE_URL"] = test_dsn
    command.upgrade(cfg, "head")

    yield test_dsn

    admin = sa.create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture()
def sync_engine(migrated_db_url: str) -> Iterator[sa.Engine]:
    engine = sa.create_engine(migrated_db_url)
    yield engine
    engine.dispose()
```

- [ ] **Step 3: Verify the fixture file parses**

Run: `cd backend && uv run python -c "import ast; ast.parse(open('tests/integration/conftest.py').read()); print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/__init__.py backend/tests/integration/conftest.py
git commit -m "test(integration): real-DB Alembic migration fixture"
```

---

## Task 9: Schema-correctness, round-trip, and autogen-diff tests

**Files:**
- Create: `backend/tests/integration/test_schema_baseline.py`

**Interfaces:**
- Consumes: `migrated_db_url`, `sync_engine` from Task 8.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_schema_baseline.py`:

```python
"""Schema baseline: the migrated DB must match the ORM models (SP-1)."""

import os

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def _include_object(object_, name, type_, reflected, compare_to):
    """Mirror of migrations/env.py include_object (kept local to avoid importing
    env.py, which executes Alembic context at module top-level)."""
    return type_ not in ("index", "check_constraint")


def _inspector(engine: sa.Engine) -> sa.Inspector:
    return sa.inspect(engine)


def test_persons_uses_created_by_clan_id(sync_engine: sa.Engine) -> None:
    cols = {c["name"] for c in _inspector(sync_engine).get_columns("persons")}
    assert "created_by_clan_id" in cols
    assert "origin_clan_id" not in cols


def test_identity_claims_uses_reviewer_note(sync_engine: sa.Engine) -> None:
    cols = {c["name"] for c in _inspector(sync_engine).get_columns("identity_claims")}
    assert "reviewer_note" in cols
    assert "reasoning" not in cols


def test_no_enum_types_remain(sync_engine: sa.Engine) -> None:
    with sync_engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT typname FROM pg_type WHERE typname IN "
                "('gender_type','document_type','event_type','clan_role','notification_status')"
            )
        ).fetchall()
    assert rows == []


def test_edge_person_fks_are_restrict(sync_engine: sa.Engine) -> None:
    # confdeltype 'r' = RESTRICT in pg_constraint
    with sync_engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT c.conname, c.confdeltype "
                "FROM pg_constraint c JOIN pg_class t ON c.conrelid = t.oid "
                "WHERE c.contype = 'f' AND t.relname IN ('marriages','parent_child') "
                "AND c.confrelid = 'persons'::regclass"
            )
        ).fetchall()
    assert len(rows) == 4
    assert all(deltype == "r" for _, deltype in rows), rows


def test_invitation_has_status_and_accepted_by(sync_engine: sa.Engine) -> None:
    cols = {c["name"] for c in _inspector(sync_engine).get_columns("clan_invitations")}
    assert {"status", "accepted_by"} <= cols
    indexes = {i["name"] for i in _inspector(sync_engine).get_indexes("clan_invitations")}
    assert "uq_clan_invitations_pending" in indexes


def test_person_insert_and_select_roundtrip(sync_engine: sa.Engine) -> None:
    """A real INSERT/SELECT on persons proves the app's columns exist."""
    with sync_engine.begin() as conn:
        clan_id = conn.execute(
            sa.text(
                "INSERT INTO clans (name, slug, created_by) "
                "VALUES ('Test', 'test-clan', gen_random_uuid()) RETURNING id"
            )
        ).scalar_one()
        person_id = conn.execute(
            sa.text(
                "INSERT INTO persons (full_name, gender, created_by_clan_id, created_by) "
                "VALUES ('Nguyễn Văn A', 'male', :clan, gen_random_uuid()) RETURNING id"
            ),
            {"clan": clan_id},
        ).scalar_one()
        got = conn.execute(
            sa.text("SELECT full_name FROM persons WHERE id = :id"), {"id": person_id}
        ).scalar_one()
    assert got == "Nguyễn Văn A"


def test_migration_round_trip(migrated_db_url: str) -> None:
    """downgrade base then upgrade head must succeed on the already-migrated DB."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", migrated_db_url)
    os.environ["DATABASE_URL"] = migrated_db_url
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


def test_autogenerate_has_no_table_or_column_diff(migrated_db_url: str) -> None:
    """After upgrade, autogenerate must not want to add/drop/alter tables or columns."""
    os.environ["DATABASE_URL"] = migrated_db_url

    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    from app.models.base import Base

    engine = sa.create_engine(migrated_db_url)
    with engine.connect() as conn:
        mc = MigrationContext.configure(
            conn,
            opts={"include_object": _include_object, "compare_type": True},
        )
        diffs = compare_metadata(mc, Base.metadata)
    engine.dispose()

    # Target exactly the drift class that broke the app: missing/renamed tables or
    # columns. Indexes/checks are excluded by _include_object; we deliberately do
    # not gate on modify_* (server-default/type representation noise).
    drift_ops = {"add_table", "remove_table", "add_column", "remove_column"}
    drift = [d for d in diffs if isinstance(d, tuple) and d and d[0] in drift_ops]
    assert drift == [], f"unexpected schema drift: {drift}"
```

- [ ] **Step 2: Start Postgres and run the tests — expect failures before the migration edits are applied**

If running this task before Tasks 3–7 are merged, the first tests fail (e.g. `origin_clan_id` present). After Tasks 3–7, run:

Run: `cd backend && docker compose up -d pgdb && uv run pytest tests/integration/test_schema_baseline.py -v`
Expected (pre-fix): FAIL on `test_persons_uses_created_by_clan_id`, `test_no_enum_types_remain`, etc.

- [ ] **Step 3: With Tasks 1–7 applied, run again — expect all pass**

Run: `cd backend && uv run pytest tests/integration/test_schema_baseline.py -v`
Expected: all tests PASS, including `test_migration_round_trip` and `test_autogenerate_has_no_table_or_column_diff`.

- [ ] **Step 4: Full sanity — existing unit tests still pass**

Run: `cd backend && uv run pytest -m unit -q`
Expected: PASS (these are mock-based and should be unaffected).

- [ ] **Step 5: Lint the new tests**

Run: `cd backend && uvx ruff check tests/integration/`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/integration/test_schema_baseline.py
git commit -m "test(integration): assert migrated schema matches models (SP-1 done)"
```

---

## Done criteria (SP-1)

- `docker compose up -d pgdb && uv run alembic upgrade head` builds the schema with no error.
- `uv run pytest tests/integration/test_schema_baseline.py` is green, proving:
  - `persons.created_by_clan_id` / `identity_claims.reviewer_note` exist (drift gone),
  - no PG enum types remain,
  - the four edge→person FKs are `RESTRICT`,
  - invitation `status`/`accepted_by` + one-pending index exist,
  - a real person INSERT/SELECT works,
  - migration round-trips, and autogenerate shows no table/column/FK drift.
- All existing unit tests still pass.

## Notes for the executor

- If `psycopg2`/`psycopg` is not importable for the sync admin connection, it is already a dev dependency (`psycopg2-binary`); run via `uv run`.
- If local Postgres credentials differ from `postgres:password@localhost:5432`, set `TEST_PG_ADMIN_URL` before running pytest.
- Do **not** regenerate `001_initial.py` from scratch — the hand-written `f_unaccent`, trigram/full-text indexes, and `update_updated_at` triggers must be preserved.
