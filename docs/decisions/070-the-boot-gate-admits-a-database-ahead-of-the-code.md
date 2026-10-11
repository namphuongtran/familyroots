# ADR-070: The Boot Gate Admits a Database Ahead of the Code

## Status

Accepted, shipped (2026-10-11). Resolves issue #255, "A deploy that carries a migration fails
cold starts of the old deployment until the new one is live".

The issue named two answers. The maintainer chose answer 2 on 2026-10-11: the boot gate admits a
database that is *ahead* of the code. Answer 1 was not chosen: deploy with
`vercel deploy --prod --skip-domain`, migrate, then `vercel promote`. **This ADR ships with its
code**, in the same pull request. Source readings were taken at `f95c8c2` on `main` on 2026-10-11.

It amends [ADR-067](067-production-ships-on-a-published-release.md). ADR-067 narrowed the
migration window, and this ADR closes it, for deployments built with this change. ADR-067's Status
carries a dated amendment.

## Context

- **A release migrates first and deploys second** (ADR-067 § 2). `release.yml` runs
  `alembic upgrade head`, and only then `vercel deploy --prod`. The new deployment goes live when
  its build is ready. Until then the previous deployment is production, against a database that is
  already migrated.
- **The boot gate admitted exact equality only.** `migration_status()` returned `current` when
  `alembic_version` equalled the code's head, and `behind` for every other value
  (`backend/app/core/readiness.py:79`). The production lifespan raised on
  anything but `current` (`backend/app/main.py:120-126`). `/health` answered 503 on anything but
  `current` (`:406-418`).
- **Measured 2026-10-10, run 38055909194.** The release migrated production to `043`. Before the
  new build went live, a request to `familyroots-api.vercel.app/health` cold-started the previous
  deployment, `dpl_5pfBiHm7NrBEmJUupmxu4GBKFntK`, built from head `042`. Its lifespan raised
  `RuntimeError: Database is not ready (migrations: behind)`, and Vercel answered
  `FUNCTION_INVOCATION_FAILED`. The function log was read with `vercel logs --status-code 5xx`.
  **The label was wrong too.** A database at `043` under code at `042` is ahead, not behind.
- **The same rule blocked rollback.** A code rollback across a migration could not boot until
  someone ran `alembic downgrade` (`docs/ops/deployment.md`, "Rollback", before this change).
- **Answer 1 only shortens the window.** With the deployment staged, the migration still commits
  before the promote. A cold start of the old deployment between the two still raised.

## Decision

### 1. `migration_status()` places the database's revision against the code's own scripts

| Status | The database's `alembic_version` | Production boot | `GET /health` |
|---|---|---|---|
| `current` | the scripts' head | boots | 200 |
| `ahead` (new) | a revision the scripts do not know | **boots**, with one warning naming both revisions | **200** |
| `behind` | a revision the scripts know that is not the head, or no `alembic_version` (missing table or empty) | refuses | 503 |
| `unknown` | not read: the scripts are unreadable | refuses | 503 |

An unreachable database still refuses the boot, and `/health` still answers 503 with
`"database": "unreachable"`.

**"A revision I don't know" is the whole test for `ahead`.** Code cannot see a migration written
after it, so it has nothing else to compare. The new `MIGRATIONS_AHEAD` constant sits beside the
others. `MIGRATIONS_SERVABLE`, `current` and `ahead`, is the one set both the lifespan and
`/health` read. `read_migrations()` returns the status with both revisions, and the boot warning
names them. `migration_status()` returns the status alone, as before.

### 2. Every migration keeps the code already live working

Admitting `ahead` rests on an authoring rule, not on a check. `docs/ops/migrations.md` already
said "Keep every migration compatible with the code already live". This ADR makes that rule
load-bearing. **A migration that drops or renames something live code reads ships in two
releases.** The first release stops the code reading it. A later release's migration removes it.
That is the shape of ADR-067 § 5, applied to the schema.

Breaking the rule now fails differently. Before, the old deployment refused to boot. Now it boots
and fails the requests that touch what the migration changed, until the new deployment is live.

### 3. The release's health read keeps requiring `current`

`ahead` is exactly what the previous deployment answers while the new build is not live yet. So
`release.yml`'s health read passes only on `200` with `"migrations": "current"`, unchanged. Only
`current` proves that the new deployment is the one serving.

## Consequences

- **The migration cold-start window closes.** During a release that carries a migration, a cold
  start of the previous deployment boots and serves, and logs the `ahead` warning.
- **A code rollback across a migration that kept the rule boots without a downgrade.** The
  rolled-back deployment reads the database as `ahead`. `alembic downgrade` is needed only when a
  migration broke the rule (`docs/ops/deployment.md`, "Rollback").
- **This protects only a deployment built with this change.** The release that ships it still opens
  the window once if it also carries a migration, because the deployment it replaces still has the
  old gate. The same holds for rolling back to a deployment built before this change: it still
  needs the downgrade.
- **Code cannot tell a later release's revision from one that never reached `main`.** A database
  migrated from a branch reads as `ahead` too, and production boots on it. Production migrates
  only from tags that ADR-067's `verify-ref` has traced to `main`, so this ADR accepts that limit
  rather than checking it.
- **`behind` is unchanged.** A database short of the code's head still refuses a production boot,
  so a deployment whose migration did not run cannot serve.
- **The additive rule stays an authoring rule.** Nothing in CI rejects a destructive migration
  (#255, out of scope).

## Alternatives considered

- **Answer 1: stage the deployment with `--skip-domain`, migrate, then `vercel promote`.**
  Promotion is instant and needs no rebuild ("Promoting Deployments", read 2026-10-11). It
  shortens the window to the time between the migration's commit and the promote, and does not
  close it. It also leaves the rollback rule as it was. It could still be added later, with a
  health read on the staged deployment before it goes live, as its own issue.
- **Keep exact equality, and accept the window.** ADR-067 made it rarer, and the 2026-10-10
  measurement shows it costs a 500 each time.
- **Compare revision numbers, so `044` reads as later than `043`.** The `NNN_` prefix is a naming
  convention, not something Alembic orders by, and the code still could not tell a later release
  from a branch. "Not in my scripts" asks the same question without the convention.

## Verification

- **The outcome, booted.** `backend/tests/integration/test_boot_gate_database_ahead.py` runs the
  real lifespan under `APP_ENV=production` against the migrated test database, then reads
  `GET /health` through the same app. With `alembic_version` set to `999_from_a_later_release`,
  the lifespan completes. `/health` answers 200 with
  `{"status": "ok", "database": "connected", "migrations": "ahead"}`. Exactly one `app.main`
  warning names that revision and the head. Each test plants its revision inside a transaction it
  rolls back, so the shared database never sees it.
- **Negative control, 2026-10-11.** With the `ahead` branch in `read_migrations()` set back to
  `behind`, which is the equality check again, that test fails with
  `RuntimeError: Database is not ready (migrations: behind)`.
- **Inversion control, 2026-10-11.** A gate that admits everything passes the `ahead` test too. So
  two more tests boot under `APP_ENV=production`: one database at the head's parent, and one with
  `alembic_version` dropped. Both must raise. With the gate's condition planted as `if False:`,
  both fail with `DID NOT RAISE RuntimeError`.
- **The empty table.** No revision is not an unknown revision. `tests/unit/test_readiness.py`
  reads an empty `alembic_version` as `behind`. With the `database is None` clause removed, that
  test fails.
- **Live, after merge (the maintainer's).** Take this reading at the **first release after the one
  that ships this change** that carries a migration. In the previous deployment's function logs
  for the window, the boot warning naming `ahead` proves a cold start happened against the
  migrated database and was admitted. There must be no `Database is not ready` error. If neither
  line appears, no cold start happened, because a warm instance serves under the old gate too.
  Record that reading as inconclusive, not as a pass. Post it on #255.

## Related

- #255. ADR-067, which this amends. ADR-065, which moved the backend to Vercel and made the boot
  gate a per-cold-start check.
- `docs/ops/deployment.md`: "The release workflow, step by step", "The window this order leaves",
  "Rollback", "Known risks".
- `docs/ops/migrations.md`: "How migrations reach production", "Boot-time migration gate".
