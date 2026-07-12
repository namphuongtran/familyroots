"""Pure clan-export serializer — "bản sao ngàn đời" (thousand-generation copy).

No I/O, no FastAPI/SQLAlchemy imports: this module only shapes plain dicts into
the archive payload and serializes it to bytes. Kept framework-agnostic so it
can be reused by future export formats (GEDCOM, etc.) and unit-tested without a
database.

NOTE (import-linter): `app.application.export.handlers` is barred from
importing `app.services` by the "application must not import core/services"
ratchet contract (pyproject.toml), so the composition root
(`app.infrastructure.dependencies`) injects `build_clan_export`/`to_json_bytes`
into `ExportQueryHandler` as plain callables rather than the handler importing
this module directly.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

FORMAT_NAME = "familyroots-clan-export"
FORMAT_VERSION = 1

# Columns injected into `persons()` port rows by the JOIN with clan_memberships
# (see ExportQueryPort.persons docstring) — these belong on the split-out
# `clan_memberships` archive, not on the `persons` one.
_MEMBERSHIP_FIELDS = ("membership_role", "stored_generation", "is_founder", "branch_id")


def build_clan_export(
    *,
    clan: dict[str, Any],
    persons: list[dict[str, Any]],
    branches: list[dict[str, Any]],
    marriages: list[dict[str, Any]],
    parent_child: list[dict[str, Any]],
    events: list[dict[str, Any]],
    documents_manifest: list[dict[str, Any]],
    generation_map: dict[uuid.UUID, int],
    exported_at: str,
) -> dict[str, Any]:
    """Assemble the lossless clan archive payload (pure — no I/O).

    ``persons`` rows are the denormalized JOIN result produced by
    ``ExportQueryPort.persons()`` (person columns plus ``membership_role``/
    ``stored_generation``/``is_founder``/``branch_id``). This function is the
    seam that (a) injects the graph-computed đời (generation) onto each person
    from ``generation_map`` — ``None`` when the person is unreachable from any
    founder — and (b) splits the denormalized row back into separate
    ``persons`` and ``clan_memberships`` archives.
    """
    out_persons: list[dict[str, Any]] = []
    out_memberships: list[dict[str, Any]] = []
    for row in persons:
        person = {k: v for k, v in row.items() if k not in _MEMBERSHIP_FIELDS}
        person["generation"] = generation_map.get(row["id"])
        out_persons.append(person)
        out_memberships.append(
            {
                "person_id": row["id"],
                "role": row.get("membership_role"),
                "stored_generation": row.get("stored_generation"),
                "is_founder": row.get("is_founder"),
                "branch_id": row.get("branch_id"),
            }
        )

    return {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "exported_at": exported_at,
        "clan": clan,
        "persons": out_persons,
        "clan_memberships": out_memberships,
        "branches": branches,
        "marriages": marriages,
        "parent_child": parent_child,
        "events": events,
        "documents_manifest": documents_manifest,
    }


def to_json_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize the archive payload to UTF-8 JSON bytes.

    ``ensure_ascii=False`` keeps Vietnamese diacritics readable in the raw
    file; ``default=str`` covers UUID/date/datetime values that ``json``
    cannot serialize natively.
    """
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
