"""Create a new tenant (clan) schema in the database.

Usage:
    uv run python scripts/create_tenant.py --slug nguyen-phuc --name "Nguyễn Phúc"
"""

# TODO: implement in Prompt 2
# Steps:
# 1. Parse CLI arguments (slug, name)
# 2. Validate slug format (lowercase, alphanumeric + hyphens)
# 3. Connect to database
# 4. Insert row into public.clans
# 5. CREATE SCHEMA clan_{slug}
# 6. Run Alembic migrations on the new schema
# 7. Optionally seed with default data
# 8. Print success message


def main() -> None:
    """Create a new tenant schema."""
    raise NotImplementedError("TODO: implement in Prompt 2")


if __name__ == "__main__":
    main()
