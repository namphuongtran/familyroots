# Infrastructure as Code Guide

## Overview

FamilyRoots uses **Pulumi** (Python SDK) for managing cloud infrastructure and **Render** native config-as-code for backend deployment.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- [Pulumi CLI](https://www.pulumi.com/docs/install/)
- Accounts: Render, Vercel, Supabase, Firebase, Sentry

## Project Structure

```
infra/
├── pulumi/
│   ├── Pulumi.yaml           # Project definition
│   ├── Pulumi.dev.yaml       # Dev stack config
│   ├── Pulumi.staging.yaml   # Staging stack config
│   ├── Pulumi.prod.yaml      # Production stack config
│   ├── pyproject.toml        # Python dependencies
│   ├── uv.lock
│   ├── __main__.py           # Entrypoint
│   └── resources/
│       ├── vercel_project.py    # Web frontend deployment
│       ├── supabase_project.py  # Database hosting
│       ├── firebase_project.py  # Push notifications
│       └── github_settings.py   # Repo settings
├── render/
│   └── render.yaml           # Backend deployment config
├── supabase/
│   ├── migrations/           # Database migrations
│   ├── seed.sql              # Dev seed data
│   └── rls_policies.sql      # Row-level security
├── firebase/
│   └── google-services-template.json
└── sentry/
    └── sentry.properties
```

## Pulumi Setup

```bash
# Install dependencies
cd infra/pulumi
uv sync

# Login to Pulumi backend
uv run pulumi login

# Select stack
uv run pulumi stack select dev
```

## Common Commands

```bash
# Preview changes (dry run)
uv run pulumi preview

# Apply changes
uv run pulumi up

# View current state
uv run pulumi stack output

# Destroy resources (caution!)
uv run pulumi destroy
```

## Stack Configuration

Each environment has its own stack config (`Pulumi.{env}.yaml`). Set secrets with:

```bash
uv run pulumi config set --secret supabase-service-key "sk_..."
```

## Render Deployment

The backend is deployed via Render's Blueprint Spec (`render.yaml`). Changes pushed to `main` trigger auto-deploy when the deploy hook is configured.

## CI/CD Integration

The `infra-ci.yml` GitHub Actions workflow:
- On PR: runs `pulumi preview` and posts a comment
- On merge to `main`: runs `pulumi up` to apply changes

## Security Notes

- Never commit secrets — use `pulumi config set --secret`
- Service account credentials go in CI/CD secrets
- The `google-services-template.json` contains placeholders only
