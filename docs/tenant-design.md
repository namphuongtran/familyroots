# Multi-Tenant Design

## Overview

FamilyRoots uses **schema-per-tenant** isolation in PostgreSQL. Each family clan gets its own schema (`clan_{slug}`) containing all clan-specific tables.

## Schema Layout

```
PostgreSQL Database: familyroots
├── public                  # Shared tables (clans registry, users, etc.)
│   ├── clans
│   ├── users
│   └── ...
├── clan_nguyen_phuc        # Clan: Nguyễn Phúc
│   ├── members
│   ├── relationships
│   ├── documents
│   └── events
├── clan_tran_van           # Clan: Trần Văn
│   ├── members
│   ├── relationships
│   ├── documents
│   └── events
└── ...
```

## Tenant Resolution Flow

```
Request → JWT Token → Extract clan_id claim
  → TenantMiddleware → SET search_path TO clan_{slug}, public
    → All DB queries scoped to tenant schema
```

## Tenant Provisioning

When a new clan is registered:

1. Insert row into `public.clans`
2. Create schema `clan_{slug}`
3. Run migrations on the new schema
4. Seed with default data (if any)

See `backend/app/services/tenant_provisioner.py`.

## Key Considerations

- **Isolation**: Full data isolation at the database level
- **Migrations**: Alembic must support multi-schema migrations
- **Connection pooling**: `search_path` is set per-request, not per-connection
- **Supabase RLS**: Additional row-level security as defense in depth

## TODO

- Implement in Prompt 2: Full tenant provisioning flow
- Implement in Prompt 2: Alembic multi-schema migration support
- Implement in Prompt 2: Supabase RLS policies per tenant
