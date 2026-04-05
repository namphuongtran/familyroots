# Secrets

## Overview
FamilyRoots uses environment-based configuration plus provider-managed secrets for deployment.

## What to Document Here
- Which secrets live in local .env.example files versus provider secret stores
- How to rotate Supabase, Firebase, Sentry, and signing credentials
- Which secrets are required by backend, web, mobile, and infra workflows
- How to verify no secrets are committed

## Current Known Risks
- Service role keys must never reach client-side code.
- Pulumi and CI secrets need consistent naming across environments.
- Secret handling should align with the pre-commit and ignore rules.
