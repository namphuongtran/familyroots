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
│   ├── migrations/
│   ├── seed.sql
│   └── rls_policies.sql
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

Database migrations and RLS policies are managed under `supabase/`.

## Firebase

Template for `google-services.json` — actual credentials are stored as CI secrets.

## Sentry

Error tracking configuration for backend and mobile apps.
