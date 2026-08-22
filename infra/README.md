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
│   ├── seed.sql            # empty scaffold
│   └── rls_policies.sql    # NOT the deployed policies — see below
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

`supabase/migrations/` used to hold a hand-written mirror of the baseline DDL. Seed S-064
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

`rls_policies.sql` is a file of the same kind and has not been reviewed against the deployed
policy set. The policies the deployed database runs come from Alembic migrations `002` and
`027`-`036` (ADR-008, ADR-043), which leave 21 policies across 14 RLS-enabled tables at head.
`rls_policies.sql` cannot be applied to that database: run against a fresh `alembic upgrade
head` on 2026-08-22 it stopped at its first statement with `ERROR: schema "auth" does not
exist`, and the 21 policies were unchanged. Do not apply it to anything.

`seed.sql` is an unimplemented scaffold: six lines, all comments.

## Firebase

Template for `google-services.json` — actual credentials are stored as CI secrets.

## Sentry

Error tracking configuration for backend and mobile apps.
