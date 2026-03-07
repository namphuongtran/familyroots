"""Tenant middleware — inject tenant schema into request context."""

# TODO: implement in Prompt 2
#
# This middleware will:
# - Extract tenant identifier from JWT claims or X-Tenant-ID header
# - Resolve the tenant schema name (clan_{slug})
# - Validate the schema exists in PostgreSQL
# - Inject the schema name into the request state for downstream use
# - Return 404 if tenant not found
