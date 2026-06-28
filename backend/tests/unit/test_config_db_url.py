"""DATABASE_URL normalization to the canonical psycopg v3 dialect."""

import pytest

from app.core.config import Settings


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Render injects bare postgresql:// via fromDatabase.connectionString
        ("postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        # Render historically also used the postgres:// scheme
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        # Legacy developer .env files
        ("postgresql+asyncpg://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        # Old sync driver
        ("postgresql+psycopg2://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        # Already canonical — no-op
        ("postgresql+psycopg://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        # Query string preserved
        (
            "postgresql+asyncpg://u:p@host:5432/db?sslmode=require",
            "postgresql+psycopg://u:p@host:5432/db?sslmode=require",
        ),
    ],
)
def test_database_url_normalized_to_psycopg(raw: str, expected: str) -> None:
    settings = Settings(_env_file=None, DATABASE_URL=raw)
    assert expected == settings.DATABASE_URL
