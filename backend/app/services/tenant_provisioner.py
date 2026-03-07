"""Tenant provisioner — create new clan schema and resources."""

# TODO: implement in Prompt 2
#
# This service will provide:
# - provision_tenant(clan_slug: str) -> ProvisioningResult
#   1. Create PostgreSQL schema clan_{slug}
#   2. Run tenant-scoped Alembic migrations against the new schema
#   3. Register the clan in public.clans
#   4. Create isolated Supabase Storage bucket clan-{slug}-files
#   5. Return provisioning status
