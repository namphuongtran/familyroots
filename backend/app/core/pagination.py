"""Cursor-based pagination utilities.

Uses (created_at, id) composite cursor for stable pagination
even when rows are inserted mid-page.
"""

import base64
import binascii
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, asc, or_

from app.core.exceptions import AppError

# Every failure mode a hand-tampered/garbage cursor can trigger while decoding:
# bad base64 padding (binascii.Error), malformed JSON or wrong-typed values
# (ValueError), missing expected keys (KeyError), or a non-str/None where a
# str was expected (TypeError). All must surface as 400 invalid_cursor, not
# an unhandled 500.
_CURSOR_ERRORS = (binascii.Error, ValueError, KeyError, TypeError)


def encode_cursor(created_at: datetime, record_id: uuid.UUID) -> str:
    """Encode a (created_at, id) pair into a base64 cursor string."""
    payload = {"created_at": created_at.isoformat(), "id": str(record_id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Decode a base64 cursor string back into (created_at, id).

    Raises ``AppError(400, "invalid_cursor")`` for any malformed/tampered
    cursor instead of leaking the raw stdlib exception.
    """
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(payload["created_at"]), uuid.UUID(payload["id"])
    except _CURSOR_ERRORS as exc:
        raise AppError(400, "invalid_cursor") from exc


def paginate_query(query: Any, model: Any, cursor: str | None, limit: int = 20) -> Any:
    """Apply cursor filter and ordering to a SQLAlchemy select query.

    Always orders by (created_at ASC, id ASC) for stable pagination.
    Fetches ``limit + 1`` rows to detect whether more pages exist.
    """
    if cursor:
        created_at, last_id = decode_cursor(cursor)
        query = query.where(
            or_(
                model.created_at > created_at,
                and_(model.created_at == created_at, model.id > last_id),
            )
        )
    return query.order_by(asc(model.created_at), asc(model.id)).limit(limit + 1)


def encode_fields_cursor(fields: dict[str, Any]) -> str:
    """Encode an arbitrary JSON-serializable field mapping into a base64 cursor string.

    Generic counterpart to ``encode_cursor``/``decode_cursor`` for callers whose stable
    sort key isn't (created_at, id) — e.g. the persons list, which orders by
    (full_name, id). Callers are responsible for converting non-JSON-native values
    (UUID, datetime, ...) to strings before passing them in.
    """
    return base64.urlsafe_b64encode(json.dumps(fields).encode()).decode()


def decode_fields_cursor(cursor: str) -> dict[str, Any]:
    """Decode a cursor produced by ``encode_fields_cursor`` back into its field mapping.

    Raises ``AppError(400, "invalid_cursor")`` for a malformed/tampered cursor.
    Callers that extract specific keys/types out of the returned mapping (e.g.
    ``decoded["full_name"]``, ``uuid.UUID(decoded["id"])``) are responsible for
    guarding that extraction the same way — this only covers the base64/JSON decode.
    """
    try:
        payload: dict[str, Any] = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except _CURSOR_ERRORS as exc:
        raise AppError(400, "invalid_cursor") from exc
    return payload


def build_page(items: list[Any], limit: int) -> dict[str, Any]:
    """Build a paginated response envelope from a list of ORM objects.

    If ``len(items) > limit``, a cursor is generated pointing to the
    last item in the returned page so the client can fetch the next page.
    """
    has_more = len(items) > limit
    data = items[:limit]
    cursor = None
    if has_more and data:
        last = data[-1]
        cursor = encode_cursor(last.created_at, last.id)
    return {
        "data": data,
        "meta": {"cursor": cursor, "has_more": has_more, "limit": limit},
    }
