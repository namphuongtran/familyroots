# Backend Developer Guide — how to build an aggregate

This is the detail-design guide for the FastAPI backend: the conventions every bounded
context follows, and the exact recipe for adding a new one. **The Person aggregate is the
canonical reference implementation** — when this guide and another aggregate disagree,
copy Person (`app/domain/person/`, `app/application/person/`,
`app/infrastructure/persistence/person_*.py`, `app/api/v1/persons.py`,
`app/schemas/person.py`), not the outlier. Layer rules are machine-enforced by
import-linter contracts in `backend/pyproject.toml` (`uv run lint-imports`).

Paths below are relative to `backend/` unless prefixed with `docs/`.

## 1. The golden write path

One request flows route → command DTO → handler → domain entity → repository → UoW commit
→ event dispatch (audit) → response DTO.

**Domain entity** (`app/domain/person/entity.py`) — a plain `@dataclass` subclassing
`AggregateRoot` (`app/domain/shared/entity.py`, which supplies `id`, `add_event()`,
`collect_events()`). No FastAPI/SQLAlchemy/Pydantic imports — the "Domain layer is pure"
import-linter contract fails the build otherwise.

- **`create()` classmethod** is the only construction path for new records; it stamps
  `created_by=actor.user_id` and emits the `*Created` event. The bare constructor is
  reserved for mapper rehydration.
- **`_UPDATABLE_FIELDS` whitelist** — a module-level `frozenset` of client-changeable
  fields. `update(changes, actor, clan_id)` iterates `changes`, raises
  `BusinessRuleViolation("field_not_updatable", {"field": ...})` for anything not
  whitelisted, records `old_values`, `setattr`s the rest, re-runs invariants, stamps
  `updated_by`/`updated_at`, and emits `*Updated` with both `changes` and `old_values`.
- **Invariants live in `_validate_*` methods called from the write paths only** —
  deliberately *not* `__post_init__`, because the persistence mapper reconstructs the
  entity from every DB row and must not raise on pre-existing rows
  (`Person._validate_dates`, entity.py:184).
- **`soft_delete()` / `restore()`** flip `is_deleted`/`deleted_at`/`deleted_by` and emit
  `*Deleted` / `*Restored`. Deletes are soft; there is no hard-delete method.

**Domain events** (`app/domain/person/events.py`) — frozen dataclasses subclassing
`AuditableEvent` (`app/domain/shared/events.py`). `clan_id` and `actor_id` are
**required, `kw_only`** — they used to default to `uuid.uuid4()`, silently fabricating a
tenant in audit rows; never reintroduce defaults for them. Each event's `__post_init__`
fills `action` (`"person.create"`), `resource_type`, `resource_id` via
`object.__setattr__` (frozen dataclass), and `PersonUpdated` serializes
`changes`/`old_values` into `new_value`/`old_value` for the audit row.

**Commands** (`app/application/person/commands.py`) — one `@dataclass(frozen=True)` per
use case (`CreatePerson`, `UpdatePerson`, …), carrying `actor: ActorInfo`, `clan_id`, and
plain-Python payload fields. Query intents (`ListPersons`, `GetPerson`) live in the same
file.

**Handler** (`app/application/person/handlers.py`) — one class per side
(`PersonCommandHandler`, `PersonQueryHandler`), one public method per use case. The write
shape is always fetch → guard → mutate → save → commit → response:

```python
async def delete(self, cmd: DeletePerson) -> None:
    person = await self._repo.get_in_clan(cmd.person_id, cmd.clan_id)
    if not person:
        raise EntityNotFoundError("person_not_found")
    person.soft_delete(cmd.actor, cmd.clan_id)
    await self._repo.save(person)
    await self._uow.commit()
```

Handlers never touch the session directly and never construct ORM models (the
"Application must not import ORM models" contract is fully burned down — keep it that way).

**Unit of Work** (`app/infrastructure/unit_of_work.py`) — wraps the request
`AsyncSession`. `commit()` flushes, drains `collect_events()` from every tracked
aggregate, dispatches them (the `AuditLogHandler` in
`app/infrastructure/event_dispatcher.py` adds `AuditLog` rows), then commits — audit rows
land in the same transaction. A failing event handler re-raises and aborts the
transaction. The dispatcher is in-process only: never treat these as durable integration
events.

**Repository takes the UoW, not a session** (`person_repository.py`):

```python
def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
    self._uow = uow
    self._session = uow.session
```

so `save()` can call `self._uow.track(person)` itself — tracking happens at the
repository seam and cannot be forgotten by a handler. `save()` is upsert-shaped:
`session.get()` the ORM row, then `apply_to_orm` (update) or `to_orm` + `session.add`
(insert). `save_with_membership()` adds the `ClanMembership` row in the same transaction.

**Mapper trio** (`app/infrastructure/persistence/person_mapper.py`) — `to_domain(model)`,
`to_orm(entity)` (INSERT only), `apply_to_orm(entity, model)` (UPDATE only, copies only
its own `UPDATABLE_FIELDS` tuple). Rule: **mapper `UPDATABLE_FIELDS` = entity
`_UPDATABLE_FIELDS` + soft-delete/audit columns** (`is_deleted`, `deleted_at`,
`deleted_by`, `updated_by`) — and never `created_by_clan_id` (provenance; reassigning it
is a cross-clan escalation, see the comment at person_mapper.py:132).

**Route** (`app/api/v1/persons.py`) — a thin controller: parse/validate via the Pydantic
request schema, build `ActorInfo.from_jwt(current_user, role.value)`
(`app/domain/shared/value_objects.py`), construct the command, call the handler, wrap in
`{"data": ...}`. Clan context always comes from `Depends(get_current_clan_id)`
(`X-Current-Clan-Id`), never the body — `create_person` stamps
`created_by_clan_id=clan_id` explicitly.

**Wiring** (`app/infrastructure/dependencies.py`) — the composition root. One provider
per handler; module-level imports only (a missing import must be a load-time error). Write
side builds a fresh `SqlAlchemyUnitOfWork(db, create_event_dispatcher(db))`; read side
uses the `_repo_uow(db)` helper (same wrapper, no commit ever issued).

**Lightweight audit path** — CRUD-heavy modules that don't warrant a full aggregate
(documents, events, branches historically, claims) use `app/application/shared/audit.py`,
which wraps a `CrudAuditEvent` in a transient `AggregateRoot` and tracks it. Two entry
points:
- `emit_audit_event(...)` — tracks **and commits the UoW itself**. For handlers whose
  audit is the only write, or the last one.
- `track_audit_event(...)` — tracks **without committing**; the caller's own
  `await uow.commit()` (after its state change) dispatches it in the same transaction.
  For handlers that already commit their own write and would otherwise double-commit.

This is the **only** sanctioned audit-write path — every module routes through the
fail-closed `AuditLogHandler` (same-transaction + ip/user_agent enrichment from
`RequestMeta`). Claims were migrated onto `track_audit_event` (M12); the old direct
`claim_repository.add_audit` writer — which bypassed the dispatcher and so never
recorded ip/user_agent — has been retired, leaving no non-dispatcher audit writer.
Acceptable only when there are no domain invariants worth modeling; anything with real
business rules gets the full entity + events treatment.

## 2. Read path (CQRS)

**Decision rule**: writes and anything returning domain aggregates go through the
**repository port** (`app/domain/person/repository.py`, a `Protocol`); nested/aggregated
read projections go through the **query port** (`app/domain/person/query_port.py`),
implemented on a bare `AsyncSession` and returning `list[dict[str, Any]]`
(`app/infrastructure/persistence/person_query_port.py` — it validates through response
schemas and `model_dump()`s). `PersonQueryHandler` takes both; query-port methods raise
`NotImplementedError` if the port wasn't wired.

**Profiles** — list/detail endpoints accept `?profile=summary|detail|full` (route helper
`_serialize_person_by_profile`, persons.py:49): `PersonSummary` for cards, `PersonDetail`
for medium payloads, full `PersonResponse.model_dump()` otherwise.

**Sparse fields and includes** — `app/core/fieldsets.py`: `parse_includes`,
`parse_field_set`, `filter_dict`, `filter_list`. Gotcha: `parse_field_set(fields,
include=...)` **merges include tokens into the field set** so an included sub-resource is
never filtered out; the batch endpoint builds `include_union` from global `include` plus
every `include_by_id` value before calling it (persons.py:273–279). Do the same in any
endpoint combining the two.

**PII redaction** — `_PII_FIELDS = ("phone", "email")` are nulled in-place on the
response models unless the viewer is clan `admin` or the person is their own linked
person (`_redact_person_pii`, handlers.py:35). It is applied on **every read path**
(`list`, `get`, `batch`) *and* on the **update response** (an editor PATCHing a
stranger's record must not read contact PII through the echo). New aggregates with PII
must copy both call sites.

**Pagination** (`app/core/pagination.py`) — decision table:

| Sort order | Use |
|---|---|
| `(created_at, id)` — the default | `paginate_query(query, model, cursor, limit)` + `build_page(items, limit)` |
| Custom, e.g. persons' `(full_name, id)` | `encode_fields_cursor({...})` / `decode_fields_cursor` and hand-write the keyset `WHERE` (person_repository.py:114) |

Both use the **limit+1 idiom**: fetch `limit + 1` rows, `has_more = len(rows) > limit`,
return `rows[:limit]`, and only emit a cursor when `has_more`. The cursor must encode
*every* sort field — an id-only cursor skips/duplicates rows whenever id-order and
name-order disagree. List meta is always `{"cursor", "has_more", "limit"}`.

## 3. Validation & exceptions — where does a check go, what do I raise

Three layers, in order:

1. **Pydantic schema** (`app/schemas/*.py`) — per-field shape only: lengths, regex
   patterns (`gender`, `*_precision`), required-ness. No cross-field rules.
2. **Domain entity** — cross-field invariants on one aggregate
   (`Person._validate_dates`: `person.death_before_birth`). Single source of truth: the
   schema deliberately does not duplicate it, so partial PATCHes are covered too.
3. **Domain service/validator** — rules spanning multiple entities or the graph, e.g.
   `RelationshipDomainValidator` (`app/domain/relationship/validator.py`:
   `relationship.creates_cycle`, `self_parent_not_allowed`), which reads through its own
   query port and is injected into the command handler by `dependencies.py`.

**The two exception families** (yes, some class names are duplicated — pick by layer):

- `app.domain.shared.exceptions` (`DomainError` subclasses, framework-free) — raise these
  in **domain, application handlers, and domain validators**. `main.py` registers
  `domain_exception_handler` (`app/core/exceptions.py:73`) which maps them to the
  standard envelope.
- `app.core.exceptions` (`AppError` subclasses **of `HTTPException`**) — allowed only in
  `core/security.py`, `core/permissions.py`, and storage/infrastructure adapters.
  Importing `app.core.exceptions` into an application handler is wrong; the four handlers
  that still do (`auth`, `me`, `claim_handlers`, `platform_admin`) are pinned ratchet
  debt in the pyproject import-linter `ignore_imports` list, which may shrink but never
  grow.

Domain → HTTP status mapping (from `domain_exception_handler`):

| Domain exception | HTTP |
|---|---|
| `EntityNotFoundError` | 404 |
| `ForbiddenError` | 403 |
| `ConflictError` | 409 |
| `AuthenticationError` | 401 |
| `BusinessRuleViolation` | 422 |
| any other `DomainError` | 400 |

**Error codes** — machine-readable, stable, and localized. Prefer dotted
`<aggregate>.<violation>` (`person.death_before_birth`, `relationship.creates_cycle`);
flat legacy codes (`field_not_updatable`, `self_marriage_not_allowed`) exist and stay,
but don't add new ones. Every code needs an `error.<code>` entry in **all four** i18n
files (`app/i18n/{vi,en,fr,zh}.json`) — `tests/unit/test_i18n_coverage.py` greps the
codebase for raised codes and fails CI on a missing vi key or any locale drift. The code
catalog lives in `docs/contracts/error-codes.md` (per-rule detail also in
`docs/architecture/domain-rules.md`); update it in the same PR.

## 4. HistoricalDate serialization pattern

Every date in a **response** is the nested object
`{"date", "precision", "display", "lunar"}` (`app/schemas/historical_date.py`); storage
and **write DTOs** stay flat (`birth_date`, `birth_date_precision`, `birth_date_display`,
`lunar_birth_date`). To add a dated response model:

```python
_PERSON_DATE_FIELDS = {"birth_date": "lunar_birth_date", "death_date": "lunar_death_date"}

class PersonResponse(BaseModel):
    birth_date: HistoricalDate = Field(default_factory=HistoricalDate)
    ...
    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _nest_dates(cls, data: Any) -> Any:
        return coerce_response_dates(cls, data, _PERSON_DATE_FIELDS)
```

The `_DATE_FIELDS` map is `date field → lunar source attribute` (or `None` when the
aggregate has no lunar column). `coerce_response_dates` handles a dict of kwargs, an ORM
row, a domain entity, *or* another response model whose field is already a
`HistoricalDate` (pass-through) — so `PersonSummary.model_validate(full_response)`
re-validation works.

**Py3.14 gotcha**: import the module (`import datetime`, use `datetime.date`), never
`from datetime import date`, in a model with a field named `date` — under PEP 649 lazy
annotations the field name shadows the import and raises
`TypeError: unsupported operand type(s) for |` (see the NOTE in historical_date.py).

**Which construction path**: entities/ORM rows → `Model.model_validate(obj)` with
`from_attributes` (the validator nests the dates); raw scalar columns in query-port SQL →
`to_historical_date(value, precision, display, lunar)` directly (see
`SqlAlchemyPersonQueryPort.get_timeline`).

## 5. Persistence conventions

- ORM models in `app/models/`, subclassing `Base` (+ `TimestampMixin`, or
  `ClanScopedMixin` when the table carries its own `clan_id` FK). `Base.metadata` uses
  `NAMING_CONVENTION` (`app/models/base.py`) so autogenerate produces stable constraint
  names.
- `TimestampMixin` uses `server_default=func.now()` — timestamps are DB-generated, which
  is why the Person mapper's `to_orm` **omits** `created_at`/`updated_at` and why domain
  Python defaults only matter pre-flush. Column `default=` (Python-side) is not a DB
  `server_default`; be deliberate about which you want, and keep ORM nullability matched
  to the real DB column or autogenerate reports drift (see the `nationality` comment,
  `app/models/person.py:63`).
- **Clan isolation in every read, no exceptions.** There is no tenant middleware and RLS
  is not active — the repository/query layer is the enforcement point. Persons are
  clan-independent, so scope via `JOIN clan_memberships cm ON cm.person_id = p.id AND
  cm.clan_id = :clan_id`; relationship edges are scoped by their **owning** clan
  (`created_by_clan_id = :clan_id` — see `get_stats_for_persons` and the query port).
  Soft-deleted rows are excluded by default; only the restore path passes
  `include_deleted=True`.
- Raw SQL is fine in repositories when it buys index alignment — the trigram search SQL
  (`_SEARCH_SQL`, person_repository.py:27) must use `public.f_unaccent(col)`, the exact
  expression its GIN indexes are built on, and lives at module level so tests can
  EXPLAIN it.

## 6. Testing conventions

- **Unit vs integration decision rule**: pure logic, envelope shapes, DTO validation, DI
  providers → `tests/unit/` (mock rows via `tests/conftest.py` factories:
  `make_person_row`, `make_spouse_row`, `make_mock_db`). Anything touching migrations,
  SQL functions, raw SQL, indexes, or **clan isolation** → `tests/integration/` against
  real Postgres.
- The real-DB harness: `tests/integration/conftest.py` drops/creates
  `family_roots_schema_test` and applies the full Alembic chain (session-scoped
  `migrated_db_url` fixture). Needs `docker compose up -d pgdb`; override the admin DSN
  with `TEST_PG_ADMIN_URL` and the database name with `TEST_PG_DB_NAME`. **Set
  `TEST_PG_DB_NAME` whenever a second suite may run at the same time** — teardown is
  `DROP DATABASE … WITH (FORCE)`, so two runs sharing the name drop each other's schema
  mid-suite (ADR-016).
- Markers `unit` / `integration` / `slow` are registered in pyproject; asyncio mode is
  `auto`.
- **Two-sided isolation pattern**: create data in clan A and clan B, assert clan A sees
  its rows *and* clan B does not (e.g.
  `tests/integration/test_person_projection_isolation.py`: an edge owned by clan B
  referencing clan A's person must be invisible to clan A).
- **Sabotage-verified negative controls**: an isolation test must be proven to fail when
  the guard is removed — either verify it manually before committing, or encode the
  control in the test itself (see `tests/integration/test_relationship_clan_isolation.py`,
  whose docstring and "Negative control" assertions check the leak *would* reappear).

## 7. New-aggregate checklist

Build in this order (names for a hypothetical `widget` aggregate):

| # | Layer | File |
|---|---|---|
| 1 | Domain | `app/domain/widget/entity.py` (dataclass, `create()`, `_UPDATABLE_FIELDS`, `_validate_*`, soft_delete/restore) |
| 2 | Domain | `app/domain/widget/events.py` (`WidgetCreated/Updated/Deleted/Restored`, subclass `AuditableEvent`) |
| 3 | Domain | `app/domain/widget/repository.py` (Protocol + filter dataclasses) — and `query_port.py` if you need dict projections |
| 4 | ORM | `app/models/widget.py` + import it in `app/models/__init__.py` (autogenerate must see it) |
| 5 | Migration | `uv run alembic revision --autogenerate -m "..."` → rename to `NNN_short_slug` (revision id **≤32 chars**, one linear chain) |
| 6 | Application | `app/application/widget/commands.py`, `handlers.py` |
| 7 | Infrastructure | `app/infrastructure/persistence/widget_mapper.py`, `widget_repository.py` (takes the UoW), `widget_query_port.py` |
| 8 | Schemas | `app/schemas/widget.py` (Create/Update requests, Response with HistoricalDate validator if dated) |
| 9 | Wiring | providers in `app/infrastructure/dependencies.py` |
| 10 | API | `app/api/v1/widgets.py`, registered in `app/api/v1/router.py` |
| 11 | i18n | `error.<code>` in all four `app/i18n/*.json` |
| 12 | Docs | `docs/contracts/rest-widgets-api.md`, error codes in `docs/contracts/error-codes.md`, ADR if architectural |
| 13 | Tests | unit + two-sided integration isolation tests |

**Import-linter obligations**: your new modules must satisfy every contract with zero new
`ignore_imports` entries — the ratchet lists may shrink, never grow. Concretely: domain
imports nothing outer; application imports domain (+ schemas) only — not
`app.core.exceptions`, and not `app.core.pagination` either (the Person handler's
`encode_fields_cursor` import is *pinned debt*; put cursor encode/decode in the
repository or route instead); routes never import SQLAlchemy or `app.models`.

**RBAC verb → role decision**: reads = `RequireViewer`; create/update = `RequireEditor`;
delete/restore = `RequireAdmin` (persons). Known deliberate deviations: person **update**
uses `RequireViewer` because the handler grants viewers a self-edit carve-out on a
whitelist of own-profile fields (handlers.py:118); **event delete is `RequireEditor`**,
not admin (`app/api/v1/events.py:168`) — events are low-stakes editor-managed content.
Pick per-verb deliberately and document deviations in the route comment.

**Quality gate** — run all five before claiming done:

```bash
uv run pytest -q && uvx ruff check . && uvx ruff format --check . \
  && uv run mypy app/ tests/ && uv run lint-imports
```

## 8. Known inconsistencies — do not copy these

- **Three hand-synced field whitelists**: entity `_UPDATABLE_FIELDS`, mapper
  `UPDATABLE_FIELDS`, and the `PersonUpdateRequest` schema fields must be kept in sync by
  hand (plus the viewer self-edit `allowed_fields` set in the handler). Adding a column
  means touching all of them; nothing enforces agreement.
- **Two response-serialization idioms** coexist: `Response.model_validate(entity)` →
  `model_dump()` (write side, list/get) vs query-port dicts merged into the response
  dict. Worse, `GET /persons/search` hand-builds its dict in the route with a **flat ISO
  `birth_date`**, bypassing schemas and the HistoricalDate contract. New endpoints should
  always go through a response schema.
- **`app/services/` is a semi-live legacy layer** (translator, notification, scheduler,
  tree_builder, relationship_descriptor) with relaxed mypy. New aggregates go through
  `application/` + `infrastructure/`; only cross-cutting concerns belong here.
- **`ActorInfo.role`'s comment mentions `"super_admin"`** (value_objects.py:19), but
  routes only ever pass `ClanRole` values (`viewer|editor|admin`); super-admin flows
  through a separate gate and never reaches `ActorInfo`.
- `PersonDetailComposite` (schemas/person.py:252) documents the include-composite shape
  but the routes build that dict manually; it is not actually used for serialization.
