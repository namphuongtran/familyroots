"""Tenant schema resolver — maps request to clan schema."""

# TODO: implement in Prompt 2
#
# This module will provide:
# - resolve_tenant(request) -> str — extract tenant slug from JWT or header
# - get_tenant_schema(clan_slug: str) -> str — return "clan_{slug}" schema name
# - validate_tenant_exists(schema_name: str) -> bool — check schema exists in DB
