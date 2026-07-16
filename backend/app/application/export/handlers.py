"""Clan export use-case handler.

Orchestrates the archival query port + storage presigning + the pure
serializer (injected as plain callables — see the note in
`app.services.clan_export` on why this handler cannot import that module
directly) into the final (filename, media_type, body) tuple a route can stream
straight back as a raw `fastapi.Response` (this endpoint is envelope-exempt).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.application.export.ports import ExportQueryPort
from app.domain.document.repository import DEFAULT_PRESIGN_TTL, StoragePort
from app.domain.shared.exceptions import EntityNotFoundError

# Plain-callable seams for the pure serializers (`app.services.clan_export`,
# `app.services.gedcom_export`), injected by the composition root
# (`app.infrastructure.dependencies`) rather than imported here — see this
# module's docstring.
BuildClanExportFn = Callable[..., dict[str, Any]]
ToJsonBytesFn = Callable[[dict[str, Any]], bytes]
BuildGedcomFn = Callable[..., str]


def filename_slug(slug: str) -> str:
    """An ASCII/header-safe filename component from a clan slug.

    The slug lands in a Content-Disposition header, which is latin-1 only —
    a diacritic slug (created before slug input validation existed) raised
    UnicodeEncodeError → 500, and a double quote broke the quoted filename.
    Transliterate (đ→d, then NFKD-strip accents), keep [a-z0-9-], collapse
    hyphens, and never return an empty component.
    """
    transliterated = slug.replace("đ", "d").replace("Đ", "D")
    ascii_only = unicodedata.normalize("NFKD", transliterated).encode("ascii", "ignore").decode()
    cleaned = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]+", "-", ascii_only.lower())).strip("-")
    return cleaned or "clan"


class ExportQueryHandler:
    """Read-only handler for the clan export use case."""

    def __init__(
        self,
        port: ExportQueryPort,
        storage: StoragePort,
        build_clan_export: BuildClanExportFn,
        to_json_bytes: ToJsonBytesFn,
        build_gedcom: BuildGedcomFn,
    ) -> None:
        self._port = port
        self._storage = storage
        self._build_clan_export = build_clan_export
        self._to_json_bytes = to_json_bytes
        self._build_gedcom = build_gedcom

    async def export_clan(self, clan_id: uuid.UUID, fmt: str) -> tuple[str, str, bytes]:
        """Build the full clan archive. Returns (filename, media_type, body).

        ``fmt="json"`` (lossless archive, keeps soft-deleted rows flagged)
        and ``fmt="gedcom"`` (GEDCOM 5.5.1 interop view, drops soft-deleted
        rows) are both implemented; anything else 500s (the route's query
        pattern already rejects other values with a 422 before reaching
        here).
        """
        clan = await self._port.clan(clan_id)
        if not clan:
            raise EntityNotFoundError("clan_not_found", {"clan_id": str(clan_id)})

        persons = await self._port.persons(clan_id)
        branches = await self._port.branches(clan_id)
        marriages = await self._port.marriages(clan_id)
        parent_child = await self._port.parent_child(clan_id)
        generation_map = await self._port.generation_map(clan_id)

        if fmt == "gedcom":
            gedcom_text = self._build_gedcom(
                clan=clan,
                persons=persons,
                marriages=marriages,
                parent_child=parent_child,
                branches=branches,
                generation_map=generation_map,
            )
            filename = f"{filename_slug(clan['slug'])}-gia-pha-{date.today().isoformat()}.ged"
            return filename, "text/x-gedcom", gedcom_text.encode("utf-8")

        if fmt != "json":
            raise NotImplementedError(f"export format '{fmt}' is not yet supported")

        now = datetime.now(UTC)
        events = await self._port.events(clan_id)
        documents = await self._port.documents(clan_id)
        documents_manifest = await self._presign_manifest(documents, now)

        payload = self._build_clan_export(
            clan=clan,
            persons=persons,
            branches=branches,
            marriages=marriages,
            parent_child=parent_child,
            events=events,
            documents_manifest=documents_manifest,
            generation_map=generation_map,
            exported_at=now.isoformat(),
        )
        body = self._to_json_bytes(payload)
        filename = f"{filename_slug(clan['slug'])}-gia-pha-{date.today().isoformat()}.json"
        return filename, "application/json", body

    async def _presign_manifest(
        self, documents: list[dict[str, Any]], now: datetime
    ) -> list[dict[str, Any]]:
        expires_at = (now + timedelta(seconds=DEFAULT_PRESIGN_TTL)).isoformat()
        manifest: list[dict[str, Any]] = []
        for doc in documents:
            download_url = await self._storage.get_presigned_url(doc["storage_path"])
            manifest.append(
                {
                    **doc,
                    "download_url": download_url,
                    "download_url_expires_at": expires_at,
                }
            )
        return manifest
