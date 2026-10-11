"""Where a document's bytes live in the private bucket, and which paths a clan may name.

Two folders under each clan's prefix (ADR-068):

    clans/{clan_id}/uploads/{file_id}.{ext}     staged: signed, maybe uploaded, not confirmed
    clans/{clan_id}/documents/{file_id}.{ext}   a confirmed document's blob

The browser uploads straight to Storage, so a confirm call names a path the client
sends back. ``parse_staged_upload_path`` is the rule that path must pass: exactly the
shape the server signed, under the acting clan's prefix and nowhere else. The clan
prefix is the storage tenancy boundary, so this is clan isolation, not formatting.
"""

from __future__ import annotations

import re
import uuid

STAGING_FOLDER = "uploads"
DOCUMENTS_FOLDER = "documents"
CLANS_ROOT = "clans"

# What safe_extension can produce, and so the only extension a staged path may carry.
_EXTENSION = r"[a-z0-9]{1,10}"
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def safe_extension(filename: str | None) -> str:
    """Derive a storage-safe file extension from a client-supplied filename.

    The extension is embedded in the storage key, whose clan prefix is the storage
    tenancy boundary. A raw filename can contain ``/`` or ``..`` (e.g.
    ``x.jpg/../../other-clan/evil``) and escape that prefix, so only lowercase
    alphanumerics from the last dot-segment are kept. Falls back to ``bin`` when
    there is no usable extension.
    """
    if not filename or "." not in filename:
        return "bin"
    raw = filename.rsplit(".", 1)[-1]
    cleaned = re.sub(r"[^a-z0-9]", "", raw.lower())[:10]
    return cleaned or "bin"


def staged_upload_path(clan_id: uuid.UUID, file_id: uuid.UUID, extension: str) -> str:
    return f"{CLANS_ROOT}/{clan_id}/{STAGING_FOLDER}/{file_id}.{extension}"


def document_path(clan_id: uuid.UUID, file_id: uuid.UUID, extension: str) -> str:
    return f"{CLANS_ROOT}/{clan_id}/{DOCUMENTS_FOLDER}/{file_id}.{extension}"


def parse_staged_upload_path(path: str, clan_id: uuid.UUID) -> tuple[uuid.UUID, str] | None:
    """Return ``(file_id, extension)`` when ``path`` is a staged path of ``clan_id``.

    Anything else returns None: another clan's prefix, the ``documents/`` folder, a
    traversal segment, an upper-case or non-canonical uuid, or any trailing text.
    ``str(uuid.UUID)`` is lowercase canonical, so the prefix built from ``clan_id``
    is the only spelling that matches.
    """
    prefix = re.escape(f"{CLANS_ROOT}/{clan_id}/{STAGING_FOLDER}/")
    match = re.fullmatch(rf"{prefix}(?P<file_id>{_UUID})\.(?P<ext>{_EXTENSION})", path)
    if match is None:
        return None
    return uuid.UUID(match["file_id"]), match["ext"]
