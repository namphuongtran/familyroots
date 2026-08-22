# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Pre-task reading**: consult the map in `../docs/README.md` before starting — API
shape changes need `../docs/contracts/`, schema changes need
`../docs/architecture/data-model.md` + `../docs/ops/migrations.md`, tree/auth work
needs `../docs/architecture/{tree-read-model,auth-flow}.md`, and architectural or
breaking changes need an ADR (`../docs/decisions/README.md`) in the same PR.
Architecture changes or new aggregates → `../docs/architecture/backend-developer-guide.md`.

## Commands

Dependencies are `uv`-managed (Python 3.14+). Only ruff runs via `uvx`; pytest, mypy, lint-imports, and alembic need `uv run` so the project's virtualenv (with the pydantic mypy plugin and app imports) is used — bare `uvx mypy` fails.

```bash
uv sync                                                # install / sync deps
uv run uvicorn app.main:app --reload                   # dev server on :8000
uv run pytest                                          # full test suite
uv run pytest tests/test_persons.py                    # single file
uv run pytest tests/test_persons.py::test_name -xvs    # single test, fail-fast, verbose
uv run pytest -m unit                                  # by marker: unit | integration | slow
uvx ruff check . && uvx ruff format .                  # lint + format (line length 100)
uv run mypy app/ tests/                                # strict typing (see pyproject overrides)
uv run lint-imports                                    # hexagonal-boundary contracts (import-linter)
uv run alembic revision --autogenerate -m "desc"       # new migration
uv run alembic upgrade head                            # apply migrations
```

Full quality gate — run all five before claiming any change done:

```bash
uv run pytest -q && uvx ruff check . && uvx ruff format --check . && uv run mypy app/ tests/ && uv run lint-imports
```

Alembic reads `DATABASE_URL` from `.env` via `app.core.config.settings` and strips `+asyncpg` for the sync migration driver (see `migrations/env.py`).

## Architecture

The backend follows **DDD + CQRS + hexagonal** layering. Layer rules are **machine-enforced** by import-linter contracts in `pyproject.toml` (`uv run lint-imports`); the "ratchet" contracts pin today's known debt via `ignore_imports` lists that may shrink but never grow — don't add entries.

- `app/domain/<aggregate>/` — pure Python aggregates, value objects, repository **ports**, domain events. **No FastAPI / SQLAlchemy / Pydantic imports allowed here.**
- `app/application/<aggregate>/` — command/query handlers (`commands.py`, `handlers.py`). Orchestrates repositories + UoW; depends only on domain.
- `app/infrastructure/` — concrete adapters: `persistence/*_repository.py` (SQLAlchemy implementations of domain ports), `persistence/*_query_port.py` (read-side CQRS projections), `unit_of_work.py`, `event_dispatcher.py`, `storage/`, `supabase_client.py`. `dependencies.py` is the composition root that wires repos + UoW + handlers into FastAPI `Depends(...)` providers.
- `app/api/v1/` — thin route handlers per aggregate, aggregated in `router.py` under `/api/v1`.
- `app/models/` — SQLAlchemy ORM models (write side). `app/schemas/` — Pydantic v2 request/response DTOs.
- `app/services/` — legacy / cross-cutting service-layer code (notifications, scheduler, translator). Newer aggregates go through `application/` + `infrastructure/`, not here. Import-linter fences it (no api/application/domain/models imports). Its background jobs (scheduler, document purge) are **sanctioned out-of-band writers**: they commit their own sessions outside UoW/domain-events — system actions with no actor, deduped/audited by their own mechanisms — and must stay the only such writers.

Aggregates currently modeled: `auth`, `branch`, `clan`, `document`, `event`, `me`, `person` (incl. claims), `platform_admin`, `relationship`, `tree`, plus `shared`.

### Unit of Work + domain events

`SqlAlchemyUnitOfWork` (`app/infrastructure/unit_of_work.py`) wraps an `AsyncSession`. Aggregates are registered via `uow.track(aggregate)`; on `commit()` the UoW flushes, **collects domain events from all tracked aggregates, dispatches them** (audit log handler, notifications, …), and then commits — so handler side-effects (e.g. audit rows) land in the same transaction. All write paths must flow through UoW + domain events; do not commit the session directly from a handler.

The dispatcher is currently the in-process `InMemoryEventDispatcher` — treat in-process events as **not** durable integration events (see repo-root "Never Do").

### Clan isolation and auth

There is intentionally **no tenant middleware**. Clan scoping comes from two layers:

1. `get_current_clan_id` dependency (`app/core/security.py`) reads the `X-Current-Clan-Id` header; users select their active clan client-side.
2. Clan isolation is enforced in the **application/repository layer**: every clan-scoped read takes `clan_id` as an explicit filter (the PRIMARY guarantee). RLS layer-2 (SP-3, ADR-008) is **active for `documents`, `events`, `branches`, `parent_child`, `marriages`, `persons`, `change_requests`, `clan_memberships`, `clan_invitations`, `notification_log`, and `user_clan_roles`** (Phases 1-11, migrations 002/026-036; `clan_settings` was Phase 10 and its table was dropped by migration 039, ADR-054): request sessions drop to the non-bypass `familyroots_app` role + set the `app.clan_id` GUC per transaction (`app/core/rls.py`); system sessions bypass. Gated by `RLS_ENABLED`. Other tables roll out table-by-table.

**Fourteen tables have RLS enabled and the fully covered count is eleven, because three of them carry policies that are not clan isolation — in three different ways.** `identity_claims` (Phase 8, migration `033`, ADR-042, seed S-012) carries one policy, `identity_claims_system_session_only FOR ALL USING (false) WITH CHECK (false)`. It compares nothing to the GUC. It is a **tripwire** for a claims query mis-wired to `get_db`; it does not catch a missing `created_by_clan_id` filter on the correct session, and the application layer is that table's only clan isolation. `audit_logs` (Phase 9, migration `034`, ADR-043, seed S-014) is clan-keyed on **reads only**: `audit_logs_sel USING (clan_id = <GUC>)`, `audit_logs_ins WITH CHECK (true)`, and **no UPDATE or DELETE policy**, which denies both commands to the request role and makes the trail append-only at the database. The permissive INSERT is not an oversight — `POST /auth/register` is unauthenticated and `POST /auth/onboard` resolves no clan, yet both write an audit row on the request session, so a clan-keyed `WITH CHECK` compares `<real clan> = NULL` and rejects registration.

So **"is RLS on and is there a policy" is not a coverage question any more, and neither is "does some policy read the GUC".** The guard in `tests/integration/test_rls_activation.py` carries **four** sets — `_CLAN_ISOLATED_TABLES`, `_REQUEST_ROLE_DENIED_TABLES`, `_PER_COMMAND_TABLES`, and `_CLAN_KEYED_MUTATION_TABLES` — asserted by `test_each_half_of_the_rls_set_matches_what_its_policies_do` (the first two) and `test_audit_logs_reads_are_clan_keyed_and_it_cannot_be_edited_or_erased` (the third, which also checks that no UPDATE or DELETE policy exists, reading `cmd` from `pg_policies` rather than inferring it from a policy name). Do not move a name between the sets to make a test pass. Measured 2026-08-22: a policy flipped to `USING (true) WITH CHECK (true)` still passes the older single-set assertion; and listing `audit_logs` as clan-isolated **also** passes, while telling a later reader its writes are confined to one clan.

**This is one of three instances of a rule that is written once, elsewhere.** The general form is that a test asserting a setting the code sets cannot fail for the reason anyone cares about. The rule, with this guard, the `web` `@theme` token probe, and the mobile `dividerTheme` field beside it, is `.claude/rules/seeds.md`, section "A test pins an outcome, not a setting". That file loads in every session. Add backend-specific evidence here; do not restate the rule here. Being per-command is not what separates the third set — `persons` is per-command (`029_rls_persons.py:56-63`) and belongs in the clan-isolated one, because all four of its `USING` clauses are clan-keyed.

**`user_clan_roles` is the third, and it is the one whose policy decides what a caller may *do*.** Phase 11, migration `036`, ADR-050, seed S-052. Four per-command policies: `user_clan_roles_sel USING (true)` and `user_clan_roles_ins WITH CHECK (true)`, both permissive **by decision**, plus clan-keyed `user_clan_roles_upd` on both halves and `user_clan_roles_del`. It is the **mirror of `audit_logs`**: a record leaks by being **read**, a capability leaks by being **written**. The reads must stay permissive because four request-session accessors run with no clan selected, starting with `get_current_clan_id` itself (`app/core/security.py:249-254`, GUC set only at `:290`). The mutations are covered because `approve_if_pending`, `delete_role_by_id`, `delete_if_pending`, and `change_role_if` (`clan_repository.py:150,184,201,219`) key on `UserClanRole.id` **alone**, with no `clan_id` predicate — a read-then-write pair, not a filter. **One trap follows, and it is ADR-038's `RETURNING` again**: `UserClanRole` inherits `TimestampMixin`, so every insert carries `RETURNING created_at, updated_at`, which Postgres matches against the **SELECT** policy. Measured 2026-08-22 — tightening `user_clan_roles_sel` breaks `POST /auth/onboard` with `new row violates row-level security policy`, **naming the wrong policy while doing it**.

**A soft-deleted person and a soft-deleted edge are two different things, and three reads still confuse them.** Measured 2026-08-22 by `tests/integration/test_edge_cascade_on_person_soft_delete.py` (seed S-020). `Person.soft_delete` (`app/domain/person/entity.py:267-280`) sets the person's own flags and emits `PersonDeleted`, and **nothing outside `app/domain/person` consumes that event** — so no cascade reaches `marriages` or `parent_child`, and those rows stay `is_deleted = false`. ADR-006's update of 2026-07-02 decided the cascade would exist; it was never built. **The reads split into two camps over the same row.** `get_timeline` (`person_query_port.py:207-216`) and the tree builder join the counterpart person and filter its `is_deleted`. `get_marriages_batch` (`:56`), `get_parent_child_links_batch` (`:81`), and `get_stats_for_persons` (`person_repository.py:260-270`) filter the **edge's** `is_deleted` only. So `GET /persons/{id}/marriages` hands a client an edge to a person the same API answers `404` for. **Ids leak, not names.** Two traps: `docs/architecture/domain-rules.md:122` says a soft-deleted person is "invisible everywhere" and that "It's not just reads" — **do not cite that sentence about the read side; it is wrong** and S-054 corrects it. And when adding any read over `marriages` or `parent_child`, filtering the edge's `is_deleted` is **half** the predicate: join the counterpart person too, the way the timeline does.

**`AuditLog` must keep `__mapper_args__ = {"eager_defaults": False}`** (ADR-038 applied by ADR-043 § 6). Postgres matches a `RETURNING` row against the SELECT policy, and `created_at`'s `server_default` otherwise makes SQLAlchemy append `RETURNING created_at` to every insert — accepted by `audit_logs_ins`, then rejected by `audit_logs_sel`. Removing the line makes `POST /auth/register` and `POST /auth/onboard` answer 500. **`NotificationLog` resolves eager defaults to True as well** and is safe only because its sole writer is the scheduler's raw `text()` INSERT on a bypassing session.

**`notification_log` is the case where the policy is inert on purpose.** Its only accessors are the anniversary scheduler's dedup `SELECT` and `INSERT` (`app/services/scheduler.py:173,201`), and the job binds its session to a bare `engine.connect()`, which is not an `RlsSession`, so no seam fires. ADR-043 took a cheap correct policy over a permanent exemption in S-015's list. **The failure a naive policy would cause here is silent** — the dedup read returns nothing, the insert is rejected, nothing raises, and clans simply stop getting giỗ reminders — so `tests/integration/test_scheduler_cross_clan_notification_log.py` runs the job against two clans and then re-reads the rows under the request role to prove the policy was live during that run.

One more trap for tests: **`tests/integration/test_auth_http_flow.py:154-160` points `get_db` at the plain privileged maker**, so that whole suite is not evidence about anything RLS-related. `tests/integration/test_audit_write_paths_no_clan_guc.py` keeps the real split and probes `SELECT current_user` on the session it hands the route.

**The seam sets `SET LOCAL ROLE` and `app.clan_id`, and nothing else** (ADR-047, which corrected ADR-008 § 2's `app.user_id` clause by dated amendment). It has **two** writers, not one: the `after_begin` event at `app/core/rls.py:63,65`, and `get_current_clan_id` at `app/core/security.py:290`, which re-applies the GUC to the transaction that began during auth before the clan was known. Adding or removing a setting means changing both. The exact set is pinned by `tests/integration/test_rls_seam_settings_pinned.py` (runtime, captured at the driver) and `tests/unit/test_rls_seam_writer_inventory.py` (the source inventory, so a third writer on an undriven path still fails) — seed S-045. Do not reach for `pg_settings` to enumerate them: measured 2026-08-22 on Postgres 18.4, neither a custom `app.*` GUC nor `role` appears there, so a catalog test would pass over a setting it cannot see.

**Before adding a table to that set, find every path that reads it with NO clan selected.** The request session drops to `familyroots_app` on *every* transaction, including one that runs before `get_current_clan_id` has set the GUC — so on such a path the policy predicate is NULL and the table reads as empty. Nothing raises. The failure looks like a successful request with missing data. Two cases were measured on 2026-08-22 — one is still open, one is resolved and shows the shape of the fix:
- **`user_clan_roles` cannot take a clan policy as it stands, and it breaks in two unlike ways.** It is the table the authorization gate reads, so a policy there does not merely hide data: it silently downgrades what the caller may do. Re-measured 2026-08-22 (S-010). **Reads fail silently:** `get_current_clan_id` reads it to decide which clan is active (`app/core/security.py:249-254`, GUC set only at `:290`), and so do `get_login_profile` (`auth_repository.py:120-137`) and `GET /me/clans` (`me_query_port.py:19-42`); login returns `200` with `clan_id: null` and `/me/clans` returns `[]`, with nothing logged. **Writes fail loudly:** `add_membership` (`auth_repository.py:69-88`) inserts the row on the same clan-less session, so both `POST /auth/onboard` flows raise `InsufficientPrivilege` and answer 500. Both halves are pinned by `tests/integration/test_rls_login_two_clans.py`. The decision is owed as **ADR-050**, seed S-052.
- **`clan_settings` is the case that ended in the table being dropped, and the lesson is about what a policy proves.** Migration `035` (Phase 10, S-010) gave it the 027 template, and every gate was green for it: RLS on, one policy, both halves clan-keyed, two-sided isolation proved at the DB layer. **None of that was evidence that anything used the table.** Nothing in `app/` ever read or wrote it except `Clan.settings`, whose result no caller consumed; nothing anywhere constructed a `ClanSettings`; no trigger created a row; and ADR-044 Measurement 5 showed the obvious row creator — an insert during clan creation, on the request session with no clan GUC — is **rejected** by that same `WITH CHECK`. So the policy guarded a reader that could not arrive, and ADR-054 (S-065, migration 039) dropped the whole table on 2026-08-22. **Two things to carry forward.** First, when you add a policy to a table nothing reads, say so at the migration and expect the question "then why does the table exist" to come back. Second, `Clan` declares four `lazy="selectin"` relationships (`app/models/clan.py:32-35`) and three of those targets carry clan policies, so the clan-less auth path routinely loads a `Clan` whose eager collections come back empty — that pattern is load-bearing, and `clan_settings` was only its clearest instance. **On an empty table, a denial test proves nothing on its own**: end every one with a privileged read proving the rows were really there.
- **`clan_invitations` had the same defect and ADR-048 fixed it — read the fix before copying it.** `POST /invitations/{token}/accept` (`app/api/v1/invitations.py:95`) has no `get_current_clan_id` by design (the invitee is not a member yet) and `get_by_token` (`invitation_repository.py:53`) has no `clan_id` predicate, because the token is the authorization. The answer was **not** to move the aggregate: `get_invitation_command_handler` is shared with create and revoke, and `get_invitation_query_handler` backs list, all three clan-scoped. Only the accept route moved, onto its own provider `get_invitation_accept_handler` (`dependencies.py:358-362`) on the privileged `get_system_db`; migration `032` then gave the table the standard policy. So **that route has one layer of isolation where the other three have two**, and the token is that layer. Pinned by `tests/unit/api/test_invitation_accept_session_wiring.py` and `tests/integration/test_invitation_accept_no_clan_context.py`. Two consequences for later work: any test that drives accept over HTTP must override `get_system_db` as well as `get_db`, and S-014's `audit_logs` policies must count this route among the privileged writers.
- **`identity_claims` is the case where the clan-less path could not be moved, so the table was locked out instead.** `GET /m/claims` (`app/api/v1/claims.py:35-43`) and `DELETE /m/claims/{claim_id}` (`:51-57`) depend only on `require_active_user` and resolve no clan by design — they are cross-clan queues. `POST /persons/{person_id}/claim` (`app/api/v1/persons.py:417-424`) resolves a clan, but it is the **claimant's**, not the claimed person's, so a clan-keyed policy would reject the insert the feature exists to perform. Both handlers were already privileged (`dependencies.py:144`, `:149`), so ADR-042 kept them there and shipped a deny-all policy as a tripwire. Two traps follow. **Any test driving a claim route over HTTP must override `get_system_db` as well as `get_db`**, or it reaches the real engine. And **`tests/integration/test_claims_audit.py:73-76` points BOTH at the privileged session**, so it passes identically with or without migration 033 — it is not evidence about session wiring. `tests/integration/test_rls_phase8_identity_claims.py` keeps the real split and is.

Auth is Supabase JWT validated against the project's JWKS (cached 1h, asyncio-Lock guarded). RBAC uses `ClanRole` (`viewer < editor < admin`) via `require_role(ClanRole.EDITOR)` for hierarchical checks or `RequireClanRole(["admin","editor"])` for explicit sets — both in `app/core/permissions.py`. Roles are read from `user_clan_role` and require `is_approved=True`.

Never bypass these checks for convenience.

### API response contracts (frozen — the frontend binds these; `docs/contracts/` is the spec)

- **Success envelope**: every 2xx body is `{"data": ...}`; list endpoints add `"meta": {"cursor", "has_more", "limit"}` (single cursor-pagination scheme, opaque cursors, `(created_at, id)` ASC — the one exception is the super-admin `GET /audit-log`, which is DESC/newest-first via `paginate_query(descending=True)` per ADR-030); 204 has no body; `/health` is exempt. Adjunct info goes in `meta` (e.g. `meta.errors`, `meta.warning`), never beside `data`.
- **HistoricalDate**: every date field in responses (persons birth/death, events event_date, marriages marriage/divorce, all tree nodes) is `{"date": ISO|null, "precision": "exact|year|month|circa|unknown", "display": str|null, "lunar": str|null}` — built by `app/schemas/historical_date.py`. Clients render `date` when precision is `exact`, else `display`. Write DTOs accept `*_precision`/`*_display`. Storage has matching `*_precision`/`*_display` columns; the old `*_approx` booleans are gone.
- **đời (generation)**: always computed by the single đời authority (con theo đời cha — ADR-027): thủy tổ = 1, đời = canonical parent's đời + 1, on every tree endpoint; `clan_memberships.generation` is deprecated as a display source. Child tree nodes carry derived `mother_id`/`mother_spouse_order` for đa thê grouping, plus `pedigree_collapse_ref` (bool) marking a stub under a non-canonical in-tree parent.
- Kinship age-based terms (`relationship_descriptor.py`) are only emitted when **both** birth dates have `precision == "exact"`.

### App startup

`app/main.py::create_app` wires: custom exception handlers (`AppError`, `DomainError` → structured envelopes via `app/core/exceptions.py`), CORS, `LanguageMiddleware` (Accept-Language → locale context for i18n), optional `SentryMiddleware`, `RequestMetaMiddleware` (captures client IP/User-Agent into a ContextVar for audit-log enrichment — see `app/core/request_meta.py`), `TraceContextMiddleware` (W3C `traceparent` correlation — see below), and a `RateLimitMiddleware` scoped to `/api/v1/auth` and `/api/v1/invitations` (20 req/min/IP, same bucket; ADR-021). Lifespan initializes Sentry, loads translations, inits Firebase Admin, starts APScheduler (used for anniversary notification jobs — see `NOTIFICATION_CRON_HOUR` in `Settings`), and disposes the async engine on shutdown.

Middleware order matters — Starlette wraps the **last-added** middleware **outermost**,
so `create_app` registers in reverse of the desired execution order. Actual order
(outermost → innermost): `Prometheus → TrustedHost → CORS → TraceContext → Language →
RequestMeta → Sentry → RateLimit` (asserted by
`tests/unit/test_metrics_endpoint.py::test_documented_middleware_order_matches_reality`).
`Prometheus` is added by `Instrumentator(...).instrument(application)` — a *hidden*
`add_middleware` call — and is deliberately outermost so RED latency measures the whole
stack, at the cost of counting `TrustedHost` rejections too; keep it inside the ordering
block or the real order silently drifts from this one. `TraceContext` sits just inside
`CORS` so every log line for the request — including the rate limiter's localized 429 —
carries the trace id.

**Observability (ADR-033):** `TraceContextMiddleware` continues an inbound
`traceparent` header or starts a new W3C trace, storing it in a ContextVar
(`app/core/trace_context.py`); the response echoes `traceparent`, and CORS
`expose_headers` it so browsers can surface it to a user — except on an unhandled
500, where `ServerErrorMiddleware` (Starlette's true outermost layer, ahead of
`Prometheus`) sends the response outside `CORSMiddleware`'s wrapper: `traceparent`
is still on that response but not CORS-exposed, so a browser can't read it; the log
line and tagged Sentry event are the correlation path for that case. `JsonFormatter`
(`app/core/logging.py`) adds `trace_id`/`span_id` to every log line emitted inside a
request, plus `route`/`clan_id` where known — outside a request (scheduler, purge)
these keys are absent entirely, not null. `SentryMiddleware` additionally tags
Sentry events with `trace_id` for the pivot from an issue to log search. RED metrics
are exposed at `GET /internal/metrics` (Prometheus exposition, envelope-exempt),
gated by `METRICS_ENABLED` + `METRICS_TOKEN` (`app/core/config.py`) and the request's
`X-Metrics-Token` header; every failure path 404s (never 401/403) per ADR-021.

**`METRICS_TOKEN` hardening (ADR-040):** `metrics_token_weakness`
(`app/core/config.py`) imposes a **length** floor — ≥32 characters, ≥8 distinct —
enforced in `Settings` validation (boot fails, every environment) *and* re-checked in
the handler so a bypassed validation fails closed rather than serving a guessable
endpoint. It is not an entropy measurement; `"abcdefgh" * 4` passes. Failed attempts
run through `MetricsFailureThrottle` (`app/core/metrics_guard.py`): 5 failures per
client IP per 60s, checked **before** the token comparison so guesses stop being
evaluated. Over budget the response stays the **same bare 404** — never a 429, which
would itself confirm the endpoint exists. Only failures count, so a scraper holding
the token is never throttled. Not middleware: the ordering block above is untouched.

Docs (`/docs`, `/redoc`) are only mounted when `APP_DEBUG=true`.

### Migrations

Single-schema Alembic, one linear chain (no branches). `migrations/env.py` imports the full `app.models` package so autogenerate sees every table. The script_location is `migrations` (not the default `alembic/`). Keep revision ids ≤32 characters (the `alembic_version` column limit) — the convention is `NNN_short_slug` matching the filename.

**A new revision must be added to `../docs/ops/migrations.md` § "Current chain", and that file's `Head = ` line updated, in the same commit.** `tests/unit/test_migrations_doc_matches_alembic.py` (seed S-063) derives both sides at run time — the chain from `alembic.script.ScriptDirectory`, the claimed chain from the document — and fails on any difference: a revision on disk the document does not name, a revision the document names that is not on disk, a different order, or a stale head. It hardcodes no revision and no head, so it needs no edit when one lands; it simply starts requiring the document to name it. Added 2026-08-22, after `docs/ops/migrations.md:119` on `main` at `62a863d` read "Head = `035_rls_clan_settings`" while `036_rls_user_clan_roles.py` had already shipped a batch earlier, and nothing caught it. The document is the source an agent reads first and the migration files are the source of truth, so when the two disagree, fix the document.

### Testing

`pytest-asyncio` in `auto` mode with function-scoped loops. Markers `unit`, `integration`, `slow` are registered in `pyproject.toml`. `tests/conftest.py` provides factories for mock DB rows (`make_person_row`, etc.) used by tree-builder unit tests. Layout mirrors the app: `tests/unit/{api,domain,infrastructure}/` plus top-level integration-style `test_*.py`.

`tests/integration/` runs against a **real Postgres**: `tests/integration/conftest.py` drops/creates a throwaway `family_roots_schema_test` database and applies the full Alembic chain (session-scoped `migrated_db_url` fixture). It needs `docker compose up -d pgdb` running; override the admin DSN with `TEST_PG_ADMIN_URL` if your local Postgres differs. Prefer these real-DB tests for anything touching migrations, SQL functions, or clan isolation — and test isolation **two-sided** (clan A sees its rows; clan B does not).

**Running two suites at once**: the teardown is `DROP DATABASE … WITH (FORCE)`, which terminates other backends' connections, so two runs sharing the database name destroy each other's schema mid-suite (`AsyncConnection [BAD]` and ~100 spurious failures). Set **`TEST_PG_DB_NAME`** to a distinct value in each — one per worktree/agent, e.g. `TEST_PG_DB_NAME=family_roots_schema_test_$(basename $PWD)`. Unset, it defaults to `family_roots_schema_test`, so a single serial run needs no change. The name must be a plain unquoted Postgres identifier (`[A-Za-z_][A-Za-z0-9_]*`, ≤63 chars); anything else fails collection rather than being interpolated into the DROP.

### mypy specifics

Strict mode is on globally, but `pyproject.toml` relaxes it for `app.services.*`, several handler/persistence modules, and tests. When touching those modules, don't reintroduce strict-mode failures *elsewhere* to "fix" them locally — check the per-module overrides first.

## Configuration

All settings live in `app/core/config.py` (`pydantic-settings`, reads `.env`). Required envs are in `.env.example`; the storage layout is path-based isolation within a single Supabase bucket: `family-roots-files/clans/{clan_id}/...`.
