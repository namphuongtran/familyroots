# Migrations

## Overview
Database schema changes are managed through Alembic in the backend and must stay aligned with docs/contracts and API expectations.

## What to Document Here
- Standard migration command sequence
- Dev/staging/prod migration differences
- Preconditions for applying destructive changes
- Backfill and data correction patterns

## Current Known Risks
- Schema changes can break client contracts if docs are not updated.
- Clan isolation assumptions must be preserved in every migration.
- Migration order matters when adding new relationships or constraints.
