"""The private bucket's allowed_mime_types is the domain's ALLOWED_MIME_TYPES (ADR-068).

The browser uploads straight to ``family-roots-files``, so the bucket's list is the first
check a file meets, and ``check_upload_file`` is the rule behind it. The two lists live in
two files. If the bucket lacks a type the domain allows, every upload of that type is
refused by Storage at the PUT, after signing succeeded, which is the failure this test
exists to catch. If the bucket carries a type the domain refuses, confirm deletes the file
anyway, so the bucket was simply a weaker wall than it claims.

``supabase/config.toml`` is the declaration both the local stack and
``supabase seed buckets --linked`` read (docs/ops/supabase-hosted-project.md § 2).
"""

import tomllib
from pathlib import Path

from app.domain.document.entity import ALLOWED_MIME_TYPES

_CONFIG = Path(__file__).resolve().parents[3] / "supabase" / "config.toml"


def test_the_files_bucket_admits_exactly_the_types_the_domain_allows() -> None:
    with _CONFIG.open("rb") as file:
        buckets = tomllib.load(file)["storage"]["buckets"]
    assert set(buckets["family-roots-files"]["allowed_mime_types"]) == ALLOWED_MIME_TYPES
