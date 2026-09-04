# Infrastructure

Infrastructure-as-Code (IaC) for the FamilyRoots platform.

## Structure

```
infra/
├── pulumi/              # Pulumi IaC (Python)
│   ├── Pulumi.yaml
│   ├── Pulumi.dev.yaml
│   ├── Pulumi.staging.yaml
│   ├── Pulumi.prod.yaml
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── __main__.py
│   └── resources/
│       ├── vercel_project.py
│       ├── supabase_project.py
│       ├── firebase_project.py
│       └── github_settings.py
├── render/
│   └── render.yaml      # Render.com config-as-code
├── supabase/
│   └── seed.sql            # empty scaffold — no schema, no policies. See below
├── firebase/
│   └── google-services-template.json
└── sentry/
    └── sentry.properties
```

## Pulumi

We use [Pulumi](https://www.pulumi.com/) with Python to manage cloud resources:

- **Vercel** — Web frontend deployment
- **Firebase** — Push notifications (Cloud Messaging)
- **Supabase** — PostgreSQL database hosting
- **GitHub** — Repository settings (branch protection, secrets)

### Commands

```bash
# Preview changes
cd infra/pulumi && uv run pulumi preview

# Apply changes
cd infra/pulumi && uv run pulumi up

# Destroy stack (caution!)
cd infra/pulumi && uv run pulumi destroy
```

### Stack configuration

- `Pulumi.dev.yaml` — Development environment
- `Pulumi.staging.yaml` — Staging environment
- `Pulumi.prod.yaml` — Production environment

## Render

Backend API is deployed on [Render](https://render.com/) using native `render.yaml` config-as-code.

## Supabase

**The database schema is not managed here.** The Alembic chain under `backend/migrations/` is
the only source of truth, and `docs/ops/migrations.md` is the document that owns it.

`supabase/migrations/` used to hold a hand-written mirror of the baseline DDL. A 2026-08-22 review
deleted it on 2026-08-22. Nothing executed it and no check read it, so it had drifted past the
point of being safe to bootstrap from. Measured on 2026-08-22 by applying both sets to the same
Postgres 18 server and diffing `information_schema`:

- 27 columns exist at Alembic head and were absent from the SQL set, including every
  `*_date_precision` / `*_date_display` column, so the schema could not hold a `HistoricalDate`.
- 8 columns existed only in the SQL set, including `persons.origin_clan_id` and
  `identity_claims.reasoning` — the pre-rename names that
  `backend/tests/integration/test_schema_baseline.py:51-60` asserts must **not** be present.
- It created a `user_devices` table the Alembic chain never creates.
  `docs/architecture/data-model.md:700-702` records that table as removed as an unused duplicate.
- Its tree-traversal functions carried no clan predicate. `003_path_finder.sql` named
  `p_clan_id` once, on line 11, as a parameter, and never used it;
  `002_tree_functions.sql` contained no occurrence of `created_by_clan_id`. The Alembic
  definitions filter on both.
- It could not be applied to a plain Postgres at all: `004_fcm_tokens.sql` calls `auth.uid()`,
  and psql stopped with `ERROR: schema "auth" does not exist`.

**The RLS policy set is not managed here either.** `rls_policies.sql` was a hand-written set of
20 policies of the same kind, and **it was deleted on 2026-08-22** after review.
The policies the deployed database runs come from Alembic migrations `002` and `027`-`036`
(ADR-008, ADR-043): 20 policies over 13 RLS-enabled tables at head, counted on 2026-08-22
against a fresh `alembic upgrade head`. (`infra/README.md` previously said 21 over 14. That was
correct when it was measured and stopped being correct the same day: migration
`039_drop_clan_settings` dropped the `clan_settings` table and its one policy with it.)

That review recorded `rls_policies.sql` as an unreviewed liability. The review found three things, all
measured on 2026-08-22 against a fresh `alembic upgrade head` on Postgres 18.

- **It contradicted ADR-008 § 2 at its root.** Every policy in it keyed on `auth.uid()`.
  ADR-008 § 2 (`docs/decisions/008-rls-defense-in-depth.md:304-308`) chose app-specific GUCs
  "not `request.jwt.claims`/`auth.uid()` which require Supabase's `auth` schema", and
  [ADR-047](../docs/decisions/047-rls-seam-sets-clan-id-only.md) re-affirms that half of § 2 as
  shipped and unchanged.
- **"It cannot be applied" was true only of plain Postgres, and that was the trap.** On plain
  Postgres it stopped at statement 1 with `ERROR: schema "auth" does not exist`, which is what
  made it look inert. Given nothing more than a stub `auth.uid()` — which a real Supabase
  project supplies for free — **31 of its 32 statements applied cleanly on top of the shipped
  set**, taking `public` from 20 policies to 39. It stopped only at the last statement, on
  `storage`, which Supabase also supplies.
- **Applying it would have widened clan isolation, not replaced it.** Every policy it declared
  was PERMISSIVE, and Postgres OR's permissive policies for the same command and role. Its
  `persons_insert_editor_above` carried `WITH CHECK (auth.user_clan_role() IN
  ('admin','editor'))` and **no clan predicate at all**, beside the shipped `persons_ins` and
  its `WITH CHECK (created_by_clan_id = current_setting('app.clan_id'))`. Demonstrated at the
  database layer: a user approved `editor` in clan A **only**, on a session whose `app.clan_id`
  was clan A, inserted a row owned by clan B and it was accepted. Dropping that single policy
  and repeating the identical insert produced `ERROR: new row violates row-level security
  policy for table "persons"`.

Its `auth.user_clan_id()` helper is worth naming as the reason not to revive any of it. It
returned the **first** approved clan by `LIMIT 1` with no `ORDER BY`. This product has no "the
user's clan": a user may belong to several, and the active one arrives per request as
`X-Current-Clan-Id` and is injected as `app.clan_id` (ADR-008, ADR-047). Its sibling
`auth.user_clan_role()` had the same `LIMIT 1` shape and **was** used, by 10 of its 20 policies.

`backend/tests/unit/test_no_parallel_table_ddl_under_infra.py` now fails on any `.sql` file
under `infra/` that declares `CREATE TABLE` **or** any RLS or policy DDL. Both assert the
statement, not the path, so a differently named file in a different directory is caught too.

`seed.sql` is an unimplemented scaffold: six lines, all comments.

## Firebase

Template for `google-services.json` — actual credentials are stored as CI secrets.

## Sentry

Error tracking configuration for backend and mobile apps.
